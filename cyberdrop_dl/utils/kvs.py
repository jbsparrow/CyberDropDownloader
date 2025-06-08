# URL de-obfuscation code for kvs (Kernel Video Sharing, https://www.kernel-video-sharing.com), from yt-dlp
# https://github.com/yt-dlp/yt-dlp/blob/e1847535e28788414a25546a45bebcada2f34558/yt_dlp/extractor/generic.py
from __future__ import annotations

import re
from typing import NamedTuple

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

HASH_LENGTH = 32
VIDEO_RESOLUTION_PATTERN = re.compile(r"video_url_text:\s*'([^']+)'")
VIDEO_INFO_PATTTERN = re.compile(
    r"video_id:\s*'(?P<video_id>[^']+)'[^}]*?"
    r"license_code:\s*'(?P<license_code>[^']+)'[^}]*?"
    r"video_url:\s*'(?P<video_url>[^']+)'[^}]*?"
)


class Video(NamedTuple):
    id: str
    res: str
    url: AbsoluteHttpURL


def get_video_info(flashvars: str) -> Video | None:
    if match_id := VIDEO_INFO_PATTTERN.search(flashvars):
        video_id, license_code, url_str = match_id.groups()
        real_url = get_real_url(url_str, license_code)
        if match_res := VIDEO_RESOLUTION_PATTERN.search(flashvars):
            resolution = match_res.group(1)
        else:
            resolution = "Unknown"
        return Video(video_id, resolution, real_url)


def get_license_token(license_code: str) -> list[int]:
    license_code = license_code.removeprefix("$")
    license_values = [int(char) for char in license_code]
    modlicense = license_code.replace("0", "1")
    middle = len(modlicense) // 2
    fronthalf = int(modlicense[: middle + 1])
    backhalf = int(modlicense[middle:])
    modlicense = str(4 * abs(fronthalf - backhalf))[: middle + 1]

    return [
        (license_values[index + offset] + current) % 10
        for index, current in enumerate(map(int, modlicense))
        for offset in range(4)
    ]


def get_real_url(video_url_str: str, license_code: str) -> AbsoluteHttpURL:
    if not video_url_str.startswith("function/0/"):
        return AbsoluteHttpURL(video_url_str)  # not obfuscated

    parsed_url = AbsoluteHttpURL(video_url_str.removeprefix("function/0/"))
    license_token = get_license_token(license_code)
    hash, tail = parsed_url.parts[3][:HASH_LENGTH], parsed_url.parts[3][HASH_LENGTH:]
    indices = list(range(HASH_LENGTH))

    # Swap indices of hash according to the destination calculated from the license token
    accum = 0
    for src in reversed(range(HASH_LENGTH)):
        accum += license_token[src]
        dest = (src + accum) % HASH_LENGTH
        indices[src], indices[dest] = indices[dest], indices[src]

    new_parts = list(parsed_url.parts)
    if not parsed_url.name:
        _ = new_parts.pop()
    new_parts[3] = "".join(hash[index] for index in indices) + tail
    return parsed_url.with_path("/".join(new_parts[1:]), keep_query=True, keep_fragment=True)
