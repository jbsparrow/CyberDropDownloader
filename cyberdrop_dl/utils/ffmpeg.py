from __future__ import annotations

import asyncio
import shutil
import subprocess
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, NamedTuple

import aiofiles
import aiofiles.os

from cyberdrop_dl.utils.logger import log_debug

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager

FFMPEG_CALL_PREFIX = "ffmpeg", "-y", "-loglevel", "error"
CONCAT_INPUT_ARGS = "-f", "concat", "-safe", "0", "-i"
CODEC_COPY = "-c", "copy"


class SubProcessResult(NamedTuple):
    return_code: int | None
    stdout: str
    stderr: str
    success: bool
    command: tuple

    def as_dict(self) -> dict:
        joined_command = " ".join(self.command)
        return self._asdict() | {"command": joined_command}


class FFmpeg:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.cache_folder = self.manager.path_manager.cache_folder.resolve()
        self.version = get_ffmpeg_version()
        self.is_available = bool(self.version)

    async def concat(self, *input_files: Path, output_file: Path, same_folder: bool = True) -> SubProcessResult:
        if not self.is_available:
            raise RuntimeError("ffmpeg is not available")
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        concat_file_name = f"{now} - {output_file.name[:40]}.ffmpeg_input.txt"
        concat_file_path = self.cache_folder / concat_file_name
        await _create_concat_input_file(*input_files, file_path=concat_file_path)
        result = await _concat(concat_file_path, output_file)
        if result.success:
            if same_folder:
                folder = input_files[0].parent
                await asyncio.to_thread(shutil.rmtree, folder, True)
            else:
                await async_delete_files(concat_file_path, *input_files)
        return result


async def async_delete_files(*files: Path) -> None:
    await asyncio.gather(*[aiofiles.os.unlink(file) for file in files])


async def _create_concat_input_file(*input: Path, file_path: Path) -> None:
    # input paths MUST be absolute!!
    async with aiofiles.open(file_path, "w", encoding="utf8") as f:
        for file in input:
            await f.write(f"file '{file}'\n")


async def _concat(concat_input_file: Path, output_file: Path):
    command = *FFMPEG_CALL_PREFIX, *CONCAT_INPUT_ARGS, str(concat_input_file), *CODEC_COPY, str(output_file)
    return await _run_command(command)


async def _run_command(command: Sequence[str]) -> SubProcessResult:
    joined_command = " ".join(command)
    log_debug(f"Running ffmpeg command: {joined_command}")
    process = await asyncio.create_subprocess_exec(*command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = await process.communicate()
    return_code = process.returncode
    stdout_str = stdout.decode("utf-8", errors="ignore")
    stderr_str = stderr.decode("utf-8", errors="ignore")
    results = SubProcessResult(return_code, stdout_str, stderr_str, return_code == 0, tuple(command))
    log_debug(results.as_dict())
    return results


@lru_cache
def get_ffmpeg_version() -> str | None:
    try:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return None
        cmd = [ffmpeg_path, "-version"]
        p = subprocess.run(cmd, timeout=5, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        stdout = p.stdout.decode("utf-8", errors="ignore")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
        return None
    else:
        return stdout.split("version", 1)[-1].split("Copyright")[0].strip()
