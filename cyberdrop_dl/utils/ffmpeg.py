from __future__ import annotations

import asyncio
import json
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
CODEC_COPY = "-c", "-copy"


class SubProcessResult(NamedTuple):
    return_code: int | None
    stdout: str
    stderr: str
    command: tuple

    def as_dict(self) -> dict:
        joined_command = " ".join(self.command)
        return self._asdict() | {"command": joined_command}


class FFmpegResult(SubProcessResult):
    def as_dict(self) -> dict:
        return super().as_dict() | {"ffmpeg_version": get_ffmpeg_version()}


class FFmpeg:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.cache_folder = self.manager.path_manager.cache_folder.resolve()

    async def concat(self, *input: Path, output: Path) -> bool:
        if not is_ffmpeg_available():
            raise RuntimeError("ffmpeg is not available")
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        concat_file_name = f"{now} - {output.name[:40]}.ffmpeg_input.txt"
        concat_file_path = self.cache_folder / concat_file_name
        await _create_concat_input_file(*input, file_path=concat_file_path)
        success = await _concat(concat_file_path, output)
        if success:
            await async_delete_files(concat_file_path, *input)
        return success


async def async_delete_files(*files: Path) -> None:
    await asyncio.gather(*[aiofiles.os.unlink(file) for file in files])


async def _create_concat_input_file(*input: Path, file_path: Path) -> None:
    # input paths MUST be absolute!!
    async with aiofiles.open(file_path, "w", encoding="utf8") as f:
        for file in input:
            await f.write(f"file '{file}'\n")


async def _concat(concat_input_file: Path, output_file: Path) -> bool:
    command = *FFMPEG_CALL_PREFIX, *CONCAT_INPUT_ARGS, str(concat_input_file), *CODEC_COPY, str(output_file)
    return_code, *_ = await _run_command(command)
    return return_code == 0


async def _run_command(command: Sequence[str]) -> FFmpegResult:
    joined_command = " ".join(command)
    log_debug(f"Running ffmpeg command: {joined_command}")
    process = await asyncio.create_subprocess_exec(*command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = await process.communicate()
    return_code = process.returncode
    stdout_str = stdout.decode("utf-8", errors="ignore")
    stderr_str = stderr.decode("utf-8", errors="ignore")
    results = FFmpegResult(return_code, stdout_str, stderr_str, tuple(command))
    log_debug(json.dumps(results.as_dict(), indent=4))
    return results


def is_ffmpeg_available() -> bool:
    return bool(get_ffmpeg_version())


@lru_cache
def get_ffmpeg_version() -> str | None:
    try:
        p = subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        stdout = p.stdout.decode("utf-8", errors="ignore")
        return stdout.split("version", 1)[-1].split("Copyright")[0].strip()
    except subprocess.CalledProcessError:
        return
