# Custom implementation of a basic M3U8 Playlist
# We may want to switch to a 3 party parser in the future to support encrypted playlists. See https://github.com/globocom/m3u8

import asyncio
import re
from collections.abc import AsyncGenerator, Generator
from typing import NamedTuple

from yarl import URL

from cyberdrop_dl.clients.errors import DownloadError
from cyberdrop_dl.utils.utilities import parse_url


class M3U8Error(DownloadError): ...


class InvalidM3U8Error(M3U8Error):
    def __init__(self) -> None:
        message = "Unable to parse m3u8 content"
        super().__init__("Invalid M3U8", message)


class HlsSegment(NamedTuple):
    index: int
    name: str
    url: URL


class Format(NamedTuple):
    height: int
    width: int
    name: str


FORMATS_REGEX = re.compile(r"RESOLUTION=(?P<resolution>\d+x\d+)\n(?P<next_line>[^\n]+)")

# Custom regex patterns, from https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/downloader/hls.py
ENCRYPTED_REGEX = re.compile(r"#EXT-X-KEY:METHOD=(?!NONE|AES-128)")
LIVE_STREAM_REGEX = re.compile(r"(?m)#EXT-X-MEDIA-SEQUENCE:(?!0$)")
DRM_REGEX = re.compile(
    "|".join(
        (
            r'#EXT-X-(?:SESSION-)?KEY:.*?URI="skd://',  # Apple FairPlay
            r'#EXT-X-(?:SESSION-)?KEY:.*?KEYFORMAT="com\.apple\.streamingkeydelivery"',  # Apple FairPlay
            r'#EXT-X-(?:SESSION-)?KEY:.*?KEYFORMAT="com\.microsoft\.playready"',  # Microsoft PlayReady
            r"#EXT-X-FAXS-CM:",  # Adobe Flash Access
        )
    )
)


class M3U8:
    def __init__(self, content: str, base_url: URL | None = None) -> None:
        self.base_url = base_url
        self.content = content
        self._lines = content.strip().splitlines()
        self._suffix = ".cdl_hsl"

    @property
    def has_drm(self):
        return bool(DRM_REGEX.search(self.content))

    @property
    def is_encrypted(self):
        # Encrypted streams do not necesarily have DRM
        return bool(ENCRYPTED_REGEX.search(self.content))

    @property
    def is_live_stream(self):
        return bool(LIVE_STREAM_REGEX.search(self.content))

    @property
    def is_playlist(self):
        return bool(FORMATS_REGEX.search(self.content))

    @property
    def best_format(self) -> Format:
        try:
            return max(self.__get_formats())
        except ValueError:
            raise M3U8Error("This is not a playlist") from None

    async def gen_segments(self) -> AsyncGenerator[HlsSegment]:
        for segment in self.__gen_segments():
            yield segment
            await asyncio.sleep(0)

    async def get_all_segments(self) -> tuple[HlsSegment, ...]:
        return tuple([seg async for seg in self.gen_segments()])

    @staticmethod
    def _clean_line(line: str) -> str | None:
        # This is the only method that we may need to be update in the future, to be more robust and handle encryption
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

    # ~~~~~~~~~~~~~~~~ PRIVATES ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def __gen_segments(self) -> Generator[HlsSegment]:
        def get_last_part() -> str:
            for line in reversed(self._lines):
                if part := self._clean_line(line):
                    return part
            raise InvalidM3U8Error

        def get_parts() -> Generator[tuple[int, str]]:
            index = 0
            for line in self._lines:
                part = self._clean_line(line)
                if not part:
                    continue
                index += 1
                yield index, part

        def parse(name: str) -> URL:
            if self.base_url:
                return self.base_url / name
            return parse_url(name)

        last_segment_part = get_last_part()
        last_index_str = re.sub(r"\D", "", last_segment_part)
        padding = max(5, len(last_index_str))
        for index, part in get_parts():
            url = parse(part)
            name = f"{index:0{padding}d}{self._suffix}"
            yield HlsSegment(index, name, url)

    def __get_formats(self):
        # This is very fast, does not need to be async
        for match in FORMATS_REGEX.finditer(self.content):
            w, _, h = match.group("resolution").partition("x")
            name: str = match.group("next_line")
            yield Format(int(h), int(w), name)
