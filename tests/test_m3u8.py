from datetime import timedelta
from typing import LiteralString

import pytest

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import InvalidURLError
from cyberdrop_dl.utils import m3u8


def _variant_parser(content: str, url: AbsoluteHttpURL | str | None = None) -> m3u8.VariantM3U8Parser:
    url = url or "https://example.com/4b4ef277/playlist.m3u8"
    m3u8_obj = m3u8.M3U8(content, AbsoluteHttpURL(url))
    return m3u8.VariantM3U8Parser(m3u8_obj)


@pytest.fixture
def m3u8_content() -> LiteralString:
    return """
    #EXTM3U
    #EXT-X-VERSION:3
    #EXT-X-TARGETDURATION:10
    #EXT-X-MEDIA-SEQUENCE:0

    #EXTINF:10.000,
    media-segment-00001.ts
    #EXTINF:10.000,
    media-segment-00002.ts
    #EXTINF:8.500,
    media-segment-00003.ts
    #EXT-X-ENDLIST
    """


@pytest.fixture
def m3u8_master_content() -> LiteralString:
    return """
    #EXTM3U
    #EXT-X-VERSION:3

    #EXT-X-STREAM-INF:BANDWIDTH=1500000,RESOLUTION=640x360,CODECS="avc1.4d401f,mp4a.40.2"
    low/stream.m3u8

    #EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720,CODECS="avc1.4d402a,mp4a.40.2"
    medium/stream.m3u8

    #EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,CODECS="avc1.4d402j,mp4a.40.2"
    high/stream.m3u8
    """


@pytest.fixture
def m3u8_master_content2() -> LiteralString:
    return """
    #EXTM3U
    #EXT-X-VERSION:4

    #EXT-X-MEDIA:AUTOSELECT=YES,DEFAULT=NO,GROUP-ID="audio",LANGUAGE="en",TYPE=AUDIO,NAME="audio",URI="audio/audio.m3u8"

    #EXT-X-STREAM-INF:BANDWIDTH=4960946,AVERAGE-BANDWIDTH=4461993,CODECS="vp09.00.40.08.00.02.02.02.00,mp4a.40.2",RESOLUTION=1080x1920,FRAME-RATE=60.000,AUDIO="audio"
    vp9_1080p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=2803971,AVERAGE-BANDWIDTH=2509229,CODECS="vp09.00.31.08.00.02.02.02.00,mp4a.40.2",RESOLUTION=720x1280,FRAME-RATE=60.000,AUDIO="audio"
    vp9_720p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=1230307,AVERAGE-BANDWIDTH=1127509,CODECS="vp09.00.30.08.00.02.02.02.00,mp4a.40.2",RESOLUTION=480x854,FRAME-RATE=30.000,AUDIO="audio"
    vp9_480p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=901303,AVERAGE-BANDWIDTH=811965,CODECS="vp09.00.21.08.00.02.02.02.00,mp4a.40.2",RESOLUTION=360x640,FRAME-RATE=30.000,AUDIO="audio"
    vp9_360p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=629922,AVERAGE-BANDWIDTH=571504,CODECS="vp09.00.20.08.00.02.02.02.00,mp4a.40.2",RESOLUTION=240x426,FRAME-RATE=30.000,AUDIO="audio"
    vp9_240p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=8245366,AVERAGE-BANDWIDTH=7656815,CODECS="avc1.64002a,mp4a.40.2",RESOLUTION=1080x1920,FRAME-RATE=60.000,AUDIO="audio"
    1080p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=3878384,AVERAGE-BANDWIDTH=3558624,CODECS="avc1.640020,mp4a.40.2",RESOLUTION=720x1280,FRAME-RATE=60.000,AUDIO="audio"
    720p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=1716380,AVERAGE-BANDWIDTH=1564076,CODECS="avc1.64001f,mp4a.40.2",RESOLUTION=480x854,FRAME-RATE=30.000,AUDIO="audio"
    480p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=1181122,AVERAGE-BANDWIDTH=1072652,CODECS="avc1.64001e,mp4a.40.2",RESOLUTION=360x640,FRAME-RATE=30.000,AUDIO="audio"
    360p/video.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=738423,AVERAGE-BANDWIDTH=671683,CODECS="avc1.640015,mp4a.40.2",RESOLUTION=240x426,FRAME-RATE=30.000,AUDIO="audio"
    240p/video.m3u8"""


@pytest.mark.parametrize(
    "url, resolution, name",
    [
        ("https://example.com/4b4ef277/720p/video.m3u8", (1280, 720), "720p"),
        ("https://example.com/4b4ef277/1920x1080p/video.m3u8", (1920, 1080), "1080p"),
        ("https://example.com/4b4ef277/1920x1234p/video.m3u8", (1920, 1234), "1234p"),
        ("https://example.com/4b4ef277/4096x2160/video.m3u8", (4096, 2160), "4K"),
        ("https://example.com/480/playlist.m3u8", (640, 480), "480p"),
    ],
)
def test_get_resolution_from_url(url: str, resolution: tuple[int, int], name: str) -> None:
    result = m3u8.get_resolution_from_url(url)
    assert result == resolution
    assert result.name == name


@pytest.mark.parametrize(
    "url, exception",
    [
        ("https://example.com/780/playlist.m3u8", RuntimeError),
        ("https://example.com", RuntimeError),
        ("/example.com", AttributeError),
        ("", InvalidURLError),
    ],
)
def test_get_resolution_from_url_invalid_url(url: str, exception: type[Exception]) -> None:
    with pytest.raises(exception):
        m3u8.get_resolution_from_url(url)


@pytest.mark.parametrize(
    "codecs, result",
    [
        ("avc1.4d401f,mp4a.40.2", ("avc1", "mp4a")),
        ("hvc1.1.6.L93.B0,mp4a.40.2", ("hevc", "mp4a")),
        ("hevc1.1.6.L93.B0,mp4a.40.2", ("hevc", "mp4a")),
        ("vp09.00.10.08,opus", ("vp9", "opus")),
        ("vp10.00.10.08,opus", ("vp10", "opus")),
        ("vp9.00.10.08,opus", ("vp9", "opus")),
        ("av01.0.04M.08,opus", ("av1", "opus")),
        ("avc1.4d401f,ac-3", ("avc1", "ac-3")),
        ("avc01.4d401f,ec-3", ("avc1", "ec-3")),
        ("avc1.4d401f", ("avc1", None)),
    ],
)
def test_codecs_parse(codecs: str, result: m3u8.Codecs) -> None:
    assert m3u8.Codecs.parse(codecs) == result


def test_m3u8(m3u8_content: str) -> None:
    m3u8_obj = m3u8.M3U8(m3u8_content)
    assert m3u8_obj.total_duration == timedelta(seconds=28.5)
    assert not m3u8_obj.is_variant
    with pytest.raises(AssertionError):
        m3u8.VariantM3U8Parser(m3u8_obj)


def test_m3u8_master(m3u8_master_content: str) -> None:
    variant = _variant_parser(m3u8_master_content)
    assert len(variant.groups) == 3
    best = variant.get_best_group()
    assert best.urls.video == AbsoluteHttpURL("https://example.com/4b4ef277/high/stream.m3u8")
    assert best.urls.audio is None
    assert best.urls.subtitle is None
    assert best.resolution == (1920, 1080)
    assert best.codecs == ("avc1", "mp4a")


def test_m3u8_master_exclude_codec(m3u8_master_content: str) -> None:
    variant = _variant_parser(m3u8_master_content)
    assert variant.get_best_group(exclude="hevc")
    with pytest.raises(StopIteration):
        variant.get_best_group(exclude="avc1")
    with pytest.raises(StopIteration):
        variant.get_best_group(only="vp9")
    with pytest.raises(AssertionError):
        variant.get_best_group(only="vp9", exclude="avc1")


def test_m3u8_master2(m3u8_master_content2: str) -> None:
    variant = _variant_parser(m3u8_master_content2)
    assert len(variant.groups) == 10
    best = variant.get_best_group()
    assert best.urls.video == AbsoluteHttpURL("https://example.com/4b4ef277/vp9_1080p/video.m3u8")
    assert best.urls.audio == AbsoluteHttpURL("https://example.com/4b4ef277/audio/audio.m3u8")
    assert best.urls.subtitle is None
    assert best.resolution == (1080, 1920)
    assert best.codecs == ("vp9", "mp4a")


def test_m3u8_master2_exclude_codec(m3u8_master_content2: str) -> None:
    variant = _variant_parser(m3u8_master_content2)
    best = variant.get_best_group(exclude="vp9")
    assert best.codecs.video == "avc1"
    assert best.urls.video == AbsoluteHttpURL("https://example.com/4b4ef277/1080p/video.m3u8")
    best = variant.get_best_group(only="vp9")
    assert best.codecs.video == "vp9"
    with pytest.raises(StopIteration):
        best = variant.get_best_group(exclude=["vp9", "avc1"])
    with pytest.raises(StopIteration):
        best = variant.get_best_group(only="hevc")
    with pytest.raises(AssertionError):
        best = variant.get_best_group(only="vp9", exclude="avc1")


def test_m3u8_master2_audio(m3u8_master_content2: str) -> None:
    variant = _variant_parser(m3u8_master_content2)
    best = variant.get_best_group()
    assert best.media.filter(group_id="audio")
    assert not best.media.filter(group_id="AUDIO")
    audios = best.media.filter(type="AUDIO")
    assert len(audios) == 1
    assert audios.get_default()
    assert best.media.filter(language="en")
    assert not best.media.filter(language="jpn")


def test_m3u8_master_w_no_codecs_should_not_raise_an_error() -> None:
    content = """
    #EXTM3U
    #EXT-X-VERSION:3

    #EXT-X-STREAM-INF:BANDWIDTH=1500000,RESOLUTION=640x360
    low/stream.m3u8

    #EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
    high/stream.m3u8
    """
    groups = _variant_parser(content).groups
    assert len(groups) == 2
    for group in groups:
        assert group.codecs == (None, None)
