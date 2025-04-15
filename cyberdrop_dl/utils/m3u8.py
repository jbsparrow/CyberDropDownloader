import asyncio
import re
from collections.abc import AsyncGenerator, Generator
from typing import NamedTuple

from yarl import URL

from cyberdrop_dl.clients.errors import DownloadError
from cyberdrop_dl.utils.utilities import parse_url


class InvalidM3U8Error(DownloadError):
    def __init__(self) -> None:
        message = "Unable to parse m3u8 content"
        super().__init__("Invalid M3U8", message)


class HlsSegment(NamedTuple):
    part: str
    name: str
    url: URL


class M3U8_Playlist:  # noqa: N801
    def __init__(self, content: str, base_url: URL | None = None) -> None:
        self._base_url = base_url
        self._content = content
        self._lines = content.splitlines()
        self._suffix = ".cdl_hsl"
        self._segments: tuple[HlsSegment, ...] = ()

    def new(self, base_url: URL | None = None):
        """Creates a new playst with the same content but a new base_url"""
        return M3U8_Playlist(self._content, base_url)

    @property
    def base_url(self) -> URL | None:
        return self._base_url

    @base_url.setter
    def set_base_url(self, url: URL) -> None:
        if self._segments:
            raise ValueError("Cannot set base. Segments were already generated. Call new() instead")
        self._base_url = url

    def _gen_segments(self) -> Generator[HlsSegment]:
        """NOTE: Calling this function directly won't update the internal segments. Acces the `segments` attribute instead"""
        if self._segments:
            yield from self._segments
            return

        def get_last_part() -> str:
            for line in reversed(self._lines):
                if part := self._clean_line(line):
                    return part
            raise InvalidM3U8Error

        def get_parts() -> Generator[str]:
            for line in self._lines:
                part = self._clean_line(line)
                if not part:
                    continue
                yield part

        def parse(part: str) -> URL:
            if self._base_url:
                return self._base_url / part
            return parse_url(part)

        last_segment_part = get_last_part()
        last_index_str = re.sub(r"\D", "", last_segment_part)
        padding = max(5, len(last_index_str))
        for index, part in enumerate(get_parts(), 1):
            url = parse(part)
            name = f"{index:0{padding}d}{self._suffix}"
            yield HlsSegment(part, name, url)

    async def _async_gen_segments(self) -> AsyncGenerator[HlsSegment]:
        """NOTE: Calling this function directly won't update the internal segments, use `get_segments` instead"""
        for segment in self._gen_segments():
            yield segment
            await asyncio.sleep(0)

    @staticmethod
    def _clean_line(line: str) -> str | None:
        # This is the only method that may need to be updated in the future to be more robust
        # All other methods are final
        stripped_line = line.strip()
        if stripped_line.startswith("#"):
            # Handle audio playlist references
            if "URI=" in stripped_line:
                parts = stripped_line.split('URI="')
                if len(parts) <= 1:
                    raise InvalidM3U8Error
                uri_part = parts[1].rsplit('"', 1)[0]
                return uri_part or None
            return None
        return stripped_line or None

    @property
    def segments(self) -> tuple[HlsSegment, ...]:
        if not self._segments:
            self._segments = tuple(self._gen_segments())
        return self._segments

    async def get_segments(self) -> tuple[HlsSegment, ...]:
        if not self._segments:
            self._segments = tuple([seg async for seg in self._async_gen_segments()])
        return self._segments
