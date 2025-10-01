from __future__ import annotations

import re
from fractions import Fraction
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable

    import yarl


VIDEO_CODECS = "avc1", "avc2", "avc3", "avc4", "av1", "hevc", "hev1", "hev2", "hvc1", "hvc2", "vp8", "vp9", "vp10"
AUDIO_CODECS = "ac-3", "ec-3", "mp3", "mp4a", "opus", "vorbis"


class Codecs(NamedTuple):
    video: str | None
    audio: str | None

    @staticmethod
    def parse(codecs: str | None) -> Codecs:
        if not codecs:
            return Codecs(None, None)
        video_codec = audio_codec = None

        def match_codec(codec: str, lookup_array: Iterable[str]) -> str | None:
            codec, *_ = codec.split(".")
            clean_codec = codec[:-1].replace("0", "") + codec[-1]
            return next((key for key in lookup_array if clean_codec.startswith(key)), None)

        for codec in codecs.split(","):
            if not video_codec and (found := match_codec(codec, VIDEO_CODECS)):
                video_codec = found
            elif not audio_codec and (found := match_codec(codec, AUDIO_CODECS)):
                audio_codec = found
            if video_codec and audio_codec:
                break

        assert video_codec
        if "avc" in video_codec:
            video_codec = "avc1"
        elif "hev" in video_codec or "hvc" in video_codec:
            video_codec = "hevc"
        return Codecs(video_codec, audio_codec)


class Resolution(NamedTuple):
    width: int
    height: int

    @property
    def name(self) -> str:
        if 7600 < self.width < 8200:
            return "8K"
        if 3800 < self.width < 4100:
            return "4K"
        return f"{self.height}p"

    @property
    def aspect_ratio(self) -> Fraction:
        return Fraction(self.width, self.height)

    @staticmethod
    def parse(url_number_or_string: yarl.URL | str | int, /) -> Resolution:
        if url_number_or_string is None:
            return UNKNOWN_RESOLUTION

        if isinstance(url_number_or_string, int):
            return Resolution._from_height(url_number_or_string)

        if not isinstance(url_number_or_string, str):
            for resolution in COMMON_RESOLUTIONS:
                if str(resolution.height) in url_number_or_string.parts:
                    return resolution

            url_number_or_string = url_number_or_string.path

        # "1080p", "720i", "480P", the most common case
        if (height := url_number_or_string.rstrip("pPiI")).isdecimal():
            return Resolution._from_height(height)

        # "1920x1080", "1280X720" or "640,480"
        if match := re.search(r"(?P<width>\d+)[xX,](?P<height>\d+)", url_number_or_string):
            return Resolution(
                width=int(match.group("width")),
                height=int(match.group("height")),
            )

        #  "1080p", "720i", "480P" w regex, slower but works with substrings
        if match := re.search(r"(?<![a-zA-Z0-9])(\d+)[pPiI](?![a-zA-Z0-9])", url_number_or_string):
            return Resolution._from_height(match.group(1))

        # "2K", "4K", "8K"
        if match := re.search(r"\b([248])[kK]\b", url_number_or_string):
            height = {"2": 1440, "4": 2160, "8": 4320}[match.group(1)]
            return Resolution._from_height(height)

        raise ValueError(f"Unable to parse resolution from {url_number_or_string}")

    @staticmethod
    def _from_height(height: str | int, aspect_ratio: float = 16 / 9) -> Resolution:
        height = int(height)
        width = round(height * aspect_ratio)
        return Resolution(width, height)

    @staticmethod
    def unknown() -> Resolution:
        return UNKNOWN_RESOLUTION

    @staticmethod
    def highest() -> Resolution:
        return HIGHEST_RESOLUTION


UNKNOWN_RESOLUTION = Resolution.parse(0)
HIGHEST_RESOLUTION = Resolution(9999, 9999)


COMMON_RESOLUTIONS: Final = tuple(
    Resolution(*resolution)  # Best to worst
    for resolution in (
        (7680, 4320),
        (3840, 2160),
        (2560, 1440),
        (1920, 1080),
        (1280, 720),
        (640, 480),
        (640, 360),
        (480, 320),
        (426, 240),
        (320, 240),
        (256, 144),
    )
)
