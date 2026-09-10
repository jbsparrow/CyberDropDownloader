import contextlib
import datetime
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from cyberdrop_dl import ffmpeg
from cyberdrop_dl.url_objects import AbsoluteHttpURL


@contextlib.contextmanager
def mock_call() -> Generator[AsyncMock]:
    with patch("cyberdrop_dl.ffmpeg._run_cmd", new_callable=AsyncMock) as m:
        m.return_value = ffmpeg.SubProcessResult(
            stdout="{}",
            stderr="",
            return_code=0,
        )
        yield m


def last_call_args(mock: AsyncMock) -> list[Any]:
    return list(mock.call_args.args[0])


def get_probe_args(mock: AsyncMock) -> list[Any]:
    return last_call_args(mock)[8:]


@pytest.mark.http
async def test_probe_url_command() -> None:
    url = AbsoluteHttpURL("https://example.com/stream.m3u8")
    with mock_call() as m:
        await ffmpeg.probe_url(url)
    assert last_call_args(m) == [
        "ffprobe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-show_streams",
        "-show_format",
        "-print_format",
        "json",
        "-tls_verify",
        "1",
        "https://example.com/stream.m3u8",
    ]


@pytest.mark.http
async def test_probe_url_w_headers() -> None:
    url = AbsoluteHttpURL("https://example.com/stream.m3u8")

    with mock_call() as m:
        await ffmpeg.probe_url(
            url,
            headers={
                "Authorization": "Bearer token",
                "User-Agent": "test",
            },
        )

    args = get_probe_args(m)
    assert args == [
        "-tls_verify",
        "1",
        "https://example.com/stream.m3u8",
        "-headers",
        "Authorization: Bearer token",
        "-headers",
        "User-Agent: test",
    ]


@pytest.mark.http
async def test_probe_url_w_proxy() -> None:
    url = AbsoluteHttpURL("https://example.com/stream.m3u8")
    proxy = AbsoluteHttpURL("http://proxy.internal:8080")
    with mock_call() as m:
        await ffmpeg.probe_url(url, proxy=proxy)

    args = last_call_args(m)
    idx = args.index("-http_proxy")
    assert args[idx + 1] == "http://proxy.internal:8080"


@pytest.mark.http
async def test_probe_url_w_verify_disabled() -> None:
    url = AbsoluteHttpURL("https://example.com/stream.m3u8")
    with mock_call() as m:
        await ffmpeg.probe_url(url, verify=False)

    args = get_probe_args(m)
    assert args == ["-tls_verify", "0", "https://example.com/stream.m3u8"]


@pytest.mark.http
async def test_probe_url_proxy_headers_no_verify() -> None:
    url = AbsoluteHttpURL("https://example.com/stream.m3u8")
    proxy = AbsoluteHttpURL("http://proxy:8080")
    with mock_call() as m:
        await ffmpeg.probe_url(url, headers={"X-Custom": "value"}, proxy=proxy, verify=False)

    args = get_probe_args(m)
    assert args == [
        "-tls_verify",
        "0",
        "https://example.com/stream.m3u8",
        "-headers",
        "X-Custom: value",
        "-http_proxy",
        "http://proxy:8080",
    ]


@pytest.mark.http
async def test_ffprobe_video_url() -> None:
    output = await ffmpeg.probe_url(
        AbsoluteHttpURL("https://videos.pexels.com/video-files/29691053/12769314_360_640_60fps.mp4")
    )

    assert output.video
    assert output.video.duration == 10.5105
    assert str(output.video.duration) == "10.51"
    assert output.video.codec == "h264"
    assert output.video.bitrate == 4_014_556
    assert output.video.fps
    assert round(output.video.fps) == 60.0
    assert output.video.width == 360
    assert output.video.height == 640

    assert output.format.bitrate == 4_019_301
    assert output.format.duration == 10.5105
    assert output.format.size == 5_280_609

    tags = output.video.tags
    assert tags["language"] == "und"
    assert tags["handler_name"] == "Core Media Video"
    assert tags["encoder"] == "Lavc60.31.102 libx264"


@pytest.mark.parametrize(
    ("duration", "hours", "minutes", "seconds"),
    [
        # numbers
        (42.5, 0, 0, 42.5),
        (123, 0, 0, 123),
        # format minutes:seconds
        ("3:30", 0, 3, 30),
        ("10:07.25", 0, 10, 7.25),
        ("00:00:30.000000000", 0, 0, 30),
        # hours:minutes:seconds
        ("00:08:37.503", 0, 8, 37.503),
        ("1:23:45.6", 1, 23, 45.6),
        ("99:59:59.999", 99, 59, 59.999),
        # 60+ seconds
        ("0:0:120.5", 0, 2, 0.5),
    ],
)
def test_parse_duration(duration: str, hours: float, minutes: float, seconds: float) -> None:
    output = ffmpeg._parse_duration(duration)
    expected = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds).total_seconds()
    assert output == expected


@pytest.mark.parametrize(
    "duration",
    ["0", "0:00", "00:00:00", None, "", -1, False, "Invalid"],
)
def test_parse_null_duration(duration: str) -> None:
    output = ffmpeg._parse_duration(duration)
    assert output is None


class TestMergeSubs:
    def test_normal_merge(self, tmp_path: Path) -> None:
        srcs = [tmp_path / f"sub{i}.srt" for i in range(1, 4)]
        for p, content in zip(srcs, (b"AAA\n", b"BBB\n", b"CCC\n"), strict=True):
            p.write_bytes(content)

        out = tmp_path / "merged.srt"

        ffmpeg._concat_bytes(srcs, out)

        assert out.read_bytes() == b"AAA\nBBB\nCCC\n"

    def test_empty_input(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.srt"
        ffmpeg._concat_bytes([], out)
        assert out.read_bytes() == b""

    def test_single_file(self, tmp_path: Path) -> None:
        src = tmp_path / "subtitles.srt"
        src.write_bytes(b" test \n")
        out = tmp_path / "out.srt"
        ffmpeg._concat_bytes([src], out)
        assert out.read_bytes() == b" test \n"


@pytest.mark.parametrize(
    ("arg", "expected"),
    [
        ("Crime dAmour", r"'Crime dAmour'"),
        ("'Crime dAmour'", r"\''Crime dAmour'\'"),
        ("Crime d'Amour", r"'Crime d'\''Amour'"),
        ("  this string starts and ends with whitespaces  ", "'  this string starts and ends with whitespaces  '"),
        (r"c:\foo", r"'c:\foo'"),
    ],
)
def test_quote(arg: str, expected: str) -> None:
    assert ffmpeg.quote_concat_arg(arg) == expected
