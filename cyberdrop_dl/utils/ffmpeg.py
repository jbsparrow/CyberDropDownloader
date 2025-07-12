from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Required, Self, TypedDict, overload

import aiofiles
import aiofiles.os
from multidict import CIMultiDict
from videoprops import which_ffprobe as _builtin_ffprobe
from yarl import URL

from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import get_valid_dict, is_absolute_http_url

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence


FFPROBE_CALL_PREFIX = "ffprobe", "-hide_banner", "-loglevel", "error", "-show_streams", "-print_format", "json"
FFMPEG_CALL_PREFIX = "ffmpeg", "-y", "-loglevel", "error"
FFMPEG_FIXUP_INPUT_ARGS = "-map", "0", "-ignore_unknown", "-c", "copy", "-f", "mp4", "-movflags", "+faststart"
FFMPEG_FIXUP_AUDIO_FILTER_ARGS = "-bsf:a", "aac_adtstoasc"
MERGE_INPUT_ARGS = "-map", "0"
CONCAT_INPUT_ARGS = "-f", "concat", "-safe", "0", "-i"
CODEC_COPY = "-c", "copy"
_AVAILABLE = False


class FFmpeg:
    def __init__(self) -> None:
        self.version = get_ffmpeg_version()
        self.is_available = bool(self.version)

    async def concat(self, *input_files: Path, output_file: Path, same_folder: bool = True) -> SubProcessResult:
        if not self.is_available:
            raise RuntimeError("ffmpeg is not available")

        concat_file_path = output_file.with_suffix(output_file.suffix + ".ffmpeg_concat.txt")
        await _create_concat_input_file(*input_files, file_path=concat_file_path)
        result = await _concat(concat_file_path, output_file)
        if result.success:
            if same_folder:
                folder = input_files[0].parent
                await asyncio.to_thread(shutil.rmtree, folder, True)
            else:
                await async_delete_files(concat_file_path, *input_files)
        await asyncio.to_thread(concat_file_path.unlink)
        return result

    async def merge(self, *input_files: Path, output_file: Path) -> SubProcessResult:
        if not self.is_available:
            raise RuntimeError("ffmpeg is not available")

        result = await _merge(*input_files, output_file=output_file)
        if result.success:
            await async_delete_files(*input_files)
        return result

    @overload
    @staticmethod
    async def probe(input: Path, /) -> FFprobeResult: ...

    @overload
    @staticmethod
    async def probe(input: URL, /, *, headers: Mapping[str, str] | None = None) -> FFprobeResult: ...

    @staticmethod
    async def probe(input: Path | URL, /, *, headers: Mapping[str, str] | None = None) -> FFprobeResult:
        if isinstance(input, URL):
            assert is_absolute_http_url(input)

        elif isinstance(input, Path):
            assert input.is_absolute()
            assert not headers

        else:
            raise ValueError("Can only probe a Path or a yarl.URL")

        command = *FFPROBE_CALL_PREFIX, str(input)
        if headers:
            add_headers = []
            for name, value in headers.items():
                add_headers.extend(["-headers", f"{name}: {value}"])

            command = *command, *add_headers
        result = await _run_command(command)
        default: FFprobeOutput = {"streams": []}
        output = json.loads(result.stdout) if result.success else default
        return FFprobeResult(output)


async def async_delete_files(*files: Path) -> None:
    await asyncio.gather(*[aiofiles.os.unlink(file) for file in files])


async def _create_concat_input_file(*input: Path, file_path: Path) -> None:
    """Input paths MUST be absolute!!."""
    async with aiofiles.open(file_path, "w", encoding="utf8") as f:
        for file in input:
            await f.write(f"file '{file}'\n")


async def _fixup_concatenated_video_file(input_file: Path, output_file: Path) -> SubProcessResult:
    command = *FFMPEG_CALL_PREFIX, "-i", str(input_file), *FFMPEG_FIXUP_INPUT_ARGS
    probe_result = await FFmpeg.probe(input_file)
    if probe_result and probe_result.audio.codec_name == "aac":
        command += FFMPEG_FIXUP_AUDIO_FILTER_ARGS
    command = *command, str(output_file)
    result = await _run_command(command)
    if result.success:
        await asyncio.to_thread(input_file.unlink)
    return result


async def _concat(concat_input_file: Path, output_file: Path) -> SubProcessResult:
    concatenated_file_name = output_file.with_suffix(".concat" + output_file.suffix)
    command = *FFMPEG_CALL_PREFIX, *CONCAT_INPUT_ARGS, str(concat_input_file), *CODEC_COPY, str(concatenated_file_name)
    result = await _run_command(command)
    if not result.success:
        return result
    return await _fixup_concatenated_video_file(concatenated_file_name, output_file)


async def _merge(*input_files: Path, output_file: Path) -> SubProcessResult:
    input_args = sum([("-i", str(path)) for path in input_files], ())
    command = *FFMPEG_CALL_PREFIX, *input_args, *MERGE_INPUT_ARGS, *CODEC_COPY, str(output_file)
    return await _run_command(command)


def check_is_available() -> None:
    global _AVAILABLE
    if _AVAILABLE:
        return
    if not get_ffmpeg_version():
        raise RuntimeError("ffmpeg is not available")
    if not get_ffprobe_version():
        raise RuntimeError("ffprobe is not available") from None
    _AVAILABLE = True


@lru_cache
def which_ffmpeg() -> str | None:
    if bin_path := shutil.which("ffmpeg"):
        return bin_path


@lru_cache
def which_ffprobe() -> str | None:
    try:
        return shutil.which("ffprobe") or (_builtin_ffprobe() + "[CDL builtin]")
    except RuntimeError:
        return


def get_ffmpeg_version() -> str | None:
    return _get_bin_version(which_ffmpeg())


def get_ffprobe_version() -> str | None:
    return _get_bin_version(which_ffprobe())


@lru_cache
def _get_bin_version(bin_path: str) -> str | None:
    try:
        cmd = bin_path, "-version"
        p = subprocess.run(
            cmd, timeout=5, check=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        stdout = p.stdout.decode("utf-8", errors="ignore")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
        return
    else:
        return stdout.partition("version")[-1].partition("Copyright")[0].strip()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~ FFprobe ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


class Duration(NamedTuple):
    # "00:03:48.250000000"
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: float = 0

    @staticmethod
    def parse(duration: float | str) -> float:
        if isinstance(duration, float | int):
            return duration
        try:
            return float(duration)
        except (ValueError, TypeError):
            pass
        days, _, other_parts = duration.partition(" ")
        if days:
            days = "".join(char for char in days if char.isdigit())
        else:
            days = "0"

        time_parts = other_parts.split(":")
        missing_parts = [0 for _ in range(3 - len(time_parts))]
        seconds = float(Fraction(time_parts.pop(-1)))
        int_parts = map(int, (days, *missing_parts, *time_parts))
        return Duration(*int_parts, seconds=seconds).as_timedelta().total_seconds()

    def as_timedelta(self) -> timedelta:
        return timedelta(**self._asdict())


class StreamDict(TypedDict, total=False):
    index: Required[int]
    codec_type: Required[Literal["video", "audio", "subtitle"]]


class FFprobeOutput(TypedDict, total=False):
    streams: Required[list[StreamDict]]


class Tags(CIMultiDict[Any]): ...


class FPS(float):
    def __str__(self) -> str:
        return str(int(self)) if self.is_integer() else f"{self:.2f}"


@dataclass(frozen=True, kw_only=True)
class Stream:
    index: int
    codec_name: str
    codec_type: str
    bitrate: int | None
    duration: float | None
    tags: Tags

    @property
    def length(self) -> float | None:
        return self.duration

    @property
    def codec(self) -> str:
        return self.codec_name

    @classmethod
    def validate(cls, stream_info: Mapping[str, Any]) -> dict[str, Any]:
        info = get_valid_dict(cls, stream_info)
        tags = Tags(stream_info.get("tags", {}))
        duration: float | str | None = stream_info.get("duration") or tags.get("duration")
        bitrate = int(stream_info.get("bitrate") or stream_info.get("bit_rate") or 0) or None
        duration = Duration.parse(duration) if duration else None
        return info | {"tags": tags, "duration": duration, "bitrate": bitrate}

    @classmethod
    def new(cls, stream_info: Mapping[str, Any]) -> Self:
        return cls(**cls.validate(stream_info))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"tags": dict(self.tags)}


@dataclass(frozen=True, kw_only=True)
class AudioStream(Stream):
    sample_rate: int | None
    codec_type: Literal["audio"] = "audio"

    @classmethod
    def validate(cls, stream_info: StreamDict) -> dict[str, Any]:
        sample_rate = int(float(stream_info.get("sample_rate", 0))) or None
        defaults = super().validate(stream_info)
        return defaults | {"sample_rate": sample_rate}


@dataclass(frozen=True, kw_only=True)
class VideoStream(Stream):
    width: int | None
    height: int | None
    fps: FPS | None
    resolution: str | None
    codec_type: Literal["video"] = "video"

    @classmethod
    def validate(cls, stream_info: StreamDict) -> dict[str, Any]:
        width = int(float(stream_info.get("width", 0))) or None
        height = int(float(stream_info.get("height", 0))) or None
        resolution = fps = None
        if width and height:
            resolution: str | None = f"{width}x{height}"

        if (avg_fps := stream_info.get("avg_frame_rate")) and str(avg_fps) not in {"0/0", "0", "0.0"}:
            fps: FPS | None = FPS(Fraction(avg_fps))

        defaults = super().validate(stream_info)
        return defaults | {"width": width, "height": height, "fps": fps, "resolution": resolution}


@dataclass
class FFprobeResult:
    ffprobe_output: FFprobeOutput
    streams: tuple[Stream, ...] = field(init=False)

    def __post_init__(self) -> None:
        streams: list[Stream] = []
        for stream in self.ffprobe_output.get("streams", []):
            if stream["codec_type"] == "video":
                streams.append(VideoStream.new(stream))
            elif stream["codec_type"] == "audio":
                streams.append(AudioStream.new(stream))

        self.streams = tuple(streams)

    def video_streams(self) -> Generator[VideoStream]:
        for stream in self.streams:
            if isinstance(stream, VideoStream):
                yield stream

    def audio_streams(self) -> Generator[AudioStream]:
        for stream in self.streams:
            if isinstance(stream, AudioStream):
                yield stream

    @property
    def audio(self) -> AudioStream:
        """First audio stream"""
        return next(self.audio_streams())

    @property
    def video(self) -> VideoStream:
        """First video stream"""
        return next(self.video_streams())

    def __bool__(self) -> bool:
        return bool(self.ffprobe_output.get("streams"))


# ~~~~~~~~~~~~~~~~~~~~~~ Subprocess ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


class SubProcessResult(NamedTuple):
    return_code: int | None
    stdout: str
    stderr: str
    success: bool
    command: tuple

    def as_dict(self) -> dict:
        joined_command = " ".join(self.command)
        return self._asdict() | {"command": joined_command}


async def _run_command(command: Sequence[str]) -> SubProcessResult:
    assert not isinstance(command, str)
    bin_path, cmd = command[0], command[1:]
    if bin_path == "ffmpeg":
        bin_path = which_ffmpeg()
    elif bin_path == "ffprobe":
        bin_path = which_ffprobe()
    assert bin_path
    command_ = bin_path, *cmd
    joined_command = " ".join(command_)
    log_debug(f"Running command: {joined_command}")
    process = await asyncio.create_subprocess_exec(*command_, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = await process.communicate()
    return_code = process.returncode
    stdout_str = stdout.decode("utf-8", errors="ignore")
    stderr_str = stderr.decode("utf-8", errors="ignore")
    results = SubProcessResult(return_code, stdout_str, stderr_str, return_code == 0, tuple(command_))
    log_debug(results.as_dict())
    return results
