from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import shutil
import uuid
from typing import TYPE_CHECKING, Any, Literal, Self, TypedDict

from multidict import CIMultiDict, CIMultiDictProxy

from cyberdrop_dl import aio
from cyberdrop_dl.utils import fast_cache
from cyberdrop_dl.utils.dataclass import DictDataclass

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator, Mapping, Sequence
    from pathlib import Path

    from cyberdrop_dl.url_objects import AbsoluteHttpURL


logger = logging.getLogger(__name__)

type CMD = Sequence[str | Path]


@fast_cache
def _which(program: str) -> str | None:
    return shutil.which(program)


@fast_cache
def _get_bin_version(bin_path: str) -> str | None:
    import subprocess

    try:
        stdout = subprocess.run(
            (bin_path, "-version"),
            timeout=5,
            check=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ).stdout.decode("utf-8", errors="ignore")

    except Exception:  # noqa: BLE001
        return None
    else:
        return stdout.partition("version")[-1].partition("Copyright")[0].strip()


def which_ffmpeg() -> str | None:
    return _which("ffmpeg")


def which_ffprobe() -> str | None:
    return _which("ffprobe")


def version() -> str | None:
    if bin_path := which_ffmpeg():
        return _get_bin_version(bin_path)


def ffprobe_version() -> str | None:
    if bin_path := which_ffprobe():
        return _get_bin_version(bin_path)


def is_installed() -> bool:
    return bool(version() and ffprobe_version())


async def run(args: CMD) -> SubProcessResult:
    assert args, "Supply at least 1 argument"
    if not version():
        raise RuntimeError("ffmpeg is not installed")
    cmd = "ffmpeg", "-y", "-nostats", "-loglevel", "warning", "-hide_banner", *args
    return await _run_cmd(cmd)


async def ffprobe_run(args: CMD) -> SubProcessResult:
    assert args, "Supply at least 1 argument"
    if not ffprobe_version():
        raise RuntimeError("ffprobe is not installed")
    cmd = "ffprobe", "-hide_banner", "-loglevel", "warning", "-show_streams", "-show_format", "-print_format", "json"
    return await _run_cmd((*cmd, *args))


async def _aac_dts_fix_args(audio_stream: Path) -> tuple[str, ...]:
    # Old issue of ffmpeg, fixed in v5.0
    # https://trac.ffmpeg.org/ticket/9433
    result = await probe(audio_stream)
    if result and (audio := result.audio) and audio.codec == "aac":
        return "-bsf:a", "aac_adtstoasc"
    return ()


async def merge(video: Path, audio: Path, output: Path) -> SubProcessResult:
    inputs = "-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", *(await _aac_dts_fix_args(audio))
    args = *inputs, "-movflags", "+faststart", output
    result = await run(args)
    if result.success:
        await aio.gather(_try_delete(video), _try_delete(audio))
    return result


def quote_concat_arg(arg: str) -> str:
    arg = arg.replace("'", r"'\''").replace("'''", "'")
    arg = arg[1:] if arg[0] == "'" else "'" + arg
    return arg[:-1] if arg[-1] == "'" else arg + "'"


def create_concat_doc(files: Iterable[Path]) -> str:
    "Input paths MUST be absolute!!."

    def lines():
        yield "ffconcat version 1.0"
        for file in files:
            if not file.is_absolute():
                raise ValueError("file is not an absolute path", file)
            yield f"file {quote_concat_arg(str(file))}"

    return "\n".join(lines())


async def concat(files: Sequence[Path], output: Path) -> SubProcessResult:
    """Concatenate fragments of the same video.

    All files must have the same streams (same codecs, resolution, time base, etc..)"""
    # https://trac.ffmpeg.org/wiki/Concatenate#demuxer

    concat_in = output.with_suffix(output.suffix + ".ffconcat.txt")
    concat_out = output.with_suffix(".concat" + output.suffix)
    logger.debug("Writing ffmpeg concat file to '%s'", concat_in)
    await aio.write_text(concat_in, create_concat_doc(files), encoding="utf8")

    args = "-f", "concat", "-safe", "0", "-i", concat_in, "-c", "copy", concat_out
    try:
        result = await run(args)
        if result.success:
            await aio.move(concat_out, output)
            await aio.gather(*(_try_delete(f) for f in files))
        else:
            await _try_delete(concat_out)
    finally:
        await _try_delete(concat_in)

    return result


async def optimize(file: Path) -> SubProcessResult:
    """
    - Make MP4s actual MP4s instead of MPEG-TS
    - Fix broken timestamps
    - Optimize for streaming (faststart)

    Should only be used for HLS downloads"""

    fixup_out = file.with_suffix(".fixup" + file.suffix)
    inputs = "-i", file, "-map", "0", "-ignore_unknown", "-c", "copy", "-f", "mp4", *(await _aac_dts_fix_args(file))
    args = *inputs, "-movflags", "+faststart", fixup_out
    result = await run(args)

    if result.success:
        await aio.unlink(file)
        await aio.move(fixup_out, file)
    else:
        await _try_delete(fixup_out)

    return result


async def _try_delete(file: Path) -> None:
    try:
        await aio.unlink(file, missing_ok=True)
    except OSError as e:
        logger.warning("Unable to delete '%s': %r", file, e)


async def raw_concat(files: Sequence[Path], output: Path) -> None:
    await asyncio.to_thread(_concat_bytes, files, output)
    await aio.gather(*(_try_delete(f) for f in files))


def _concat_bytes(files: Iterable[Path], output: Path) -> None:
    with output.open("wb") as out:
        for file in files:
            with file.open("rb") as fp_in:
                out.write(fp_in.read())


async def probe(file: Path, /) -> FFprobeResult:
    assert file.is_absolute()
    return await _probe([str(file)])


async def probe_url(
    url: AbsoluteHttpURL,
    /,
    *,
    headers: Mapping[str, str] | None = None,
    proxy: AbsoluteHttpURL | None = None,
    cookies: tuple[str, ...] = (),
    verify: bool = True,
) -> FFprobeResult:

    def extra_params() -> Generator[str]:
        if headers:
            yield "-headers"
            yield "".join(f"{name}: {value}\r\n" for name, value in headers.items())

        if proxy:
            # Only available since v5.0
            yield "-http_proxy"
            yield str(proxy)

        if cookies:
            # TODO: add cookies support
            pass

    args = "-tls_verify", str(int(verify)), *extra_params(), str(url)
    return await _probe(args)


async def _probe(args: CMD) -> FFprobeResult:
    result = await ffprobe_run(args)
    if not result.success:
        return _EMPTY_FFPROBE_RESULT
    return FFprobeResult.from_output(json.loads(result.stdout))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~ FFprobe ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def _parse_duration(duration: str | float | None) -> TruncatedFloat | None:
    if not duration:
        return None

    if isinstance(duration, (float, int)):
        seconds: float | int = duration

    else:
        try:
            *rest, seconds_str = duration.strip().split(":")

            seconds = float(seconds_str)
            for idx, value in enumerate(reversed(rest), 1):
                seconds += int(value) * 60**idx

        except Exception:  # noqa: BLE001
            return None

    if seconds > 0:
        return TruncatedFloat(seconds)


class FFprobeOutput(TypedDict):
    streams: list[dict[str, Any]]


class Tags(CIMultiDictProxy[Any]): ...


class TruncatedFloat(float):
    def __str__(self) -> str:
        return str(int(self)) if self.is_integer() else f"{self:.2f}"


@dataclasses.dataclass(slots=True, kw_only=True)
class Stream(DictDataclass):
    index: int
    codec: str
    codec_type: str
    bitrate: int | None
    duration: TruncatedFloat | None
    tags: Tags

    @classmethod
    def validate(cls, stream_info: Mapping[str, Any]) -> dict[str, Any]:
        info = cls.filter_dict(stream_info)
        tags = Tags(CIMultiDict(stream_info.get("tags", {})))
        return info | {
            "codec": stream_info.get("codec_name"),
            "duration": _parse_duration(stream_info.get("duration") or tags.get("duration")),
            "bitrate": int(stream_info.get("bitrate") or stream_info.get("bit_rate") or 0) or None,
            "tags": tags,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], /, **overrides: Any) -> Self:
        return super(Stream, cls).from_dict(cls.validate(data), **overrides)


@dataclasses.dataclass(slots=True, kw_only=True)
class AudioStream(Stream):
    sample_rate: int | None
    codec_type: Literal["audio"] = "audio"  # pyright: ignore[reportIncompatibleVariableOverride]

    @classmethod
    def validate(cls, stream_info: Mapping[str, Any]) -> dict[str, Any]:
        defaults = super(AudioStream, cls).validate(stream_info)
        sample_rate = int(float(stream_info.get("sample_rate", 0))) or None
        return defaults | {"sample_rate": sample_rate}


@dataclasses.dataclass(slots=True, kw_only=True)
class VideoStream(Stream):
    width: int | None
    height: int | None
    fps: TruncatedFloat | None
    resolution: str | None
    codec_type: Literal["video"] = "video"  # pyright: ignore[reportIncompatibleVariableOverride]

    @classmethod
    def validate(cls, stream_info: Mapping[str, Any]) -> dict[str, Any]:
        width = int(float(stream_info.get("width", 0))) or None
        height = int(float(stream_info.get("height", 0))) or None
        resolution = fps = None
        if width and height:
            resolution: str | None = f"{width}x{height}"

        if (avg_fps := stream_info.get("avg_frame_rate")) and str(avg_fps) not in {"0/0", "0", "0.0"}:
            from fractions import Fraction

            fps: TruncatedFloat | None = TruncatedFloat(Fraction(avg_fps))

        defaults = super(VideoStream, cls).validate(stream_info)
        return defaults | {"width": width, "height": height, "fps": fps, "resolution": resolution}


@dataclasses.dataclass(slots=True)
class Format:
    size: int | None
    bitrate: int | None
    duration: TruncatedFloat | None
    tags: Tags

    @classmethod
    def from_dict(cls, format_info: dict[str, Any]) -> Self:
        tags = Tags(CIMultiDict(format_info.get("tags", {})))

        return cls(
            size=int(float(format_info.get("size") or 0)) or None,
            duration=_parse_duration(format_info.get("duration") or tags.get("duration")),
            bitrate=int(format_info.get("bitrate") or format_info.get("bit_rate") or 0) or None,
            tags=tags,
        )


@dataclasses.dataclass(slots=True)
class FFprobeResult:
    ffprobe_output: FFprobeOutput
    streams: tuple[VideoStream | AudioStream, ...]
    format: Format

    audio: AudioStream | None = dataclasses.field(init=False)
    """First audio stream"""
    video: VideoStream | None = dataclasses.field(init=False)
    """First video stream"""

    def __post_init__(self) -> None:
        self.audio = next(self.audio_streams(), None)
        self.video = next(self.video_streams(), None)

    def __bool__(self) -> bool:
        return bool(self.streams)

    def __iter__(self) -> Iterator[Stream]:
        return iter(self.streams)

    @staticmethod
    def from_output(ffprobe_output: FFprobeOutput) -> FFprobeResult:
        def streams() -> Generator[VideoStream | AudioStream]:
            for stream in ffprobe_output.get("streams", ()):
                match stream["codec_type"]:
                    case "video":
                        yield VideoStream.from_dict(stream)
                    case "audio":
                        yield AudioStream.from_dict(stream)
                    case _:
                        pass

        return FFprobeResult(
            ffprobe_output,
            streams=tuple(streams()),
            format=Format.from_dict(ffprobe_output.get("format", {})),
        )

    def video_streams(self) -> Generator[VideoStream]:
        for stream in self.streams:
            if stream.codec_type == "video":
                yield stream

    def audio_streams(self) -> Generator[AudioStream]:
        for stream in self.streams:
            if stream.codec_type == "audio":
                yield stream


_EMPTY_FFPROBE_RESULT: FFprobeResult = FFprobeResult.from_output({"streams": []})

# ~~~~~~~~~~~~~~~~~~~~~~ Subprocess ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@dataclasses.dataclass(slots=True, frozen=True)
class SubProcessResult:
    return_code: int | None
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.return_code == 0

    __iter__ = DictDataclass.__iter__

    def __json__(self) -> dict[str, Any]:
        me = dict(self)
        try:
            stdout = json.loads(self.stdout)
        except json.JSONDecodeError:
            pass
        else:
            me["stdout"] = stdout
        return me

    def __str__(self) -> str:
        return str(self.__json__())


def _split_cmd(command: CMD) -> tuple[str, str, list[str | Path]]:
    program, *args = command

    match program:
        case "ffmpeg":
            path = which_ffmpeg()
        case "ffprobe":
            path = which_ffprobe()
        case _:
            raise ValueError(f"Unexpected program in command {command}")

    assert path
    return program, path, args


async def _run_cmd(command: CMD) -> SubProcessResult:
    assert not isinstance(command, str)
    program, path, args = _split_cmd(command)
    import asyncio.subprocess

    process_id = str(uuid.uuid4())
    logger.debug("Running %s subprocess [id=%s]:\n%s", program, process_id, (path, *map(str, args)))

    process = await asyncio.subprocess.create_subprocess_exec(
        path,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    result = SubProcessResult(
        stdout=stdout.decode("utf-8", errors="ignore"),
        stderr=stderr.decode("utf-8", errors="ignore"),
        return_code=process.returncode,
    )
    logger.debug("%s subprocess [id=%s] output:\n%s", program, process_id, result)
    return result
