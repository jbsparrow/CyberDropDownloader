import re
from collections.abc import Generator
from typing import NamedTuple

from yarl import URL

from cyberdrop_dl.clients.errors import DownloadError
from cyberdrop_dl.utils.utilities import parse_url


class InvalidM3U8Error(DownloadError):
    def __init__(self, msg: str) -> None:
        super().__init__("Invalid M3U8", msg)


class HlsSegment(NamedTuple):
    part: str
    name: str
    url: URL


class M3U8_Playlist:  # noqa: N801
    def __init__(self, content: str, base_url: URL | None = None) -> None:
        self._content = content
        self._lines = content.splitlines()
        self._base_url = base_url
        self._segments: tuple[HlsSegment, ...] = ()

    def gen_segments(self) -> Generator[HlsSegment]:
        if self._segments:
            yield from self._segments
            return

        def get_last_segment_line() -> str:
            for line in reversed(self._lines):
                if not line.startswith("#"):
                    return line.strip()
            raise InvalidM3U8Error("Unable to parse m3u8 content")

        def get_segment_lines() -> Generator[str]:
            for line in self._lines:
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                if stripped_line.startswith("#"):
                    continue
                yield stripped_line

        def parse(part: str) -> URL:
            if self._base_url:
                return self._base_url / part
            return parse_url(part)

        last_segment_part = get_last_segment_line()
        last_index_str = re.sub(r"\D", "", last_segment_part)
        padding = max(5, len(last_index_str))
        parts = get_segment_lines()
        for index, part in enumerate(parts, 1):
            url = parse(part)
            name = f"{index:0{padding}d}.cdl_hsl"
            yield HlsSegment(part, name, url)

    @property
    def segments(self) -> tuple[HlsSegment, ...]:
        if not self._segments:
            self._segments = tuple(self.gen_segments())
        return self._segments
