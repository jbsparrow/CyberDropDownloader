from __future__ import annotations

import dataclasses
import re
from collections import Counter
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_PRIMARY_URL = AbsoluteHttpURL("https://megacloud.blog")
_V3_SOURCES_URL = _PRIMARY_URL / "embed-2/v3/e-1/getSources"
_HEADERS = {"Origin": str(_PRIMARY_URL), "Referer": str(_PRIMARY_URL) + "/"}


@dataclasses.dataclass(frozen=True, slots=True)
class MegaCloudSubtitle:
    label: str
    lang_code: str
    suffix: str
    url: AbsoluteHttpURL


@dataclasses.dataclass(slots=True)
class MegaCloudVideo:
    id: str
    embed_url: AbsoluteHttpURL
    sources: tuple[AbsoluteHttpURL, ...]
    subtitles: tuple[MegaCloudSubtitle, ...]
    title: str = ""


_find_v3_client_key = re.compile(
    r'([a-zA-Z0-9]{48})|x: "([a-zA-Z0-9]{16})", y: "([a-zA-Z0-9]{16})", z: "([a-zA-Z0-9]{16})"};'
).search


class MegaCloudCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[dict[str, str]] = {
        "Embed v3": "/embed-2/v3",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "megacloud"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["embed-2", "v3", _, _]:
                return await self.embed_v3(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def embed_v3(self, scrape_item: ScrapeItem) -> None:
        canonical_url = scrape_item.url.with_query(None)
        if await self.check_complete_from_referer(canonical_url):
            return

        video = await self._request_video_source(scrape_item.url)
        scrape_item.url = canonical_url
        await self._handle_video(scrape_item, video)

    async def _handle_video(self: Crawler, scrape_item: ScrapeItem, video: MegaCloudVideo) -> None:
        m3u8_url = video.sources[0]
        m3u8, info = await self.get_m3u8_from_playlist_url(m3u8_url, headers=_HEADERS)
        filename, ext = self.get_filename_and_ext(video.id + ".mp4")
        custom_filename = self.create_custom_filename(
            video.title or video.id, ext, file_id=video.id, resolution=info.resolution
        )
        self.create_task(
            self.handle_file(
                video.embed_url,
                scrape_item,
                filename,
                ext,
                m3u8=m3u8,
                custom_filename=custom_filename,
            )
        )
        video_stem = custom_filename.removesuffix(ext)
        for sub in video.subtitles:
            sub_name, ext = self.get_filename_and_ext(f"{video_stem}.{sub.suffix}")
            self.create_task(
                self.handle_file(
                    sub.url,
                    scrape_item,
                    sub.label,
                    ext,
                    custom_filename=sub_name,
                )
            )

    async def _get_client_key(self: Crawler, embed_url: AbsoluteHttpURL) -> str:
        content = await self.request_text(embed_url, headers=_HEADERS)
        if match := _find_v3_client_key(content):
            return "".join(filter(None, match.groups()))

        raise ScrapeError(422, "Unable to extract client key")

    async def _request_video_source(self: Crawler, embed_url: AbsoluteHttpURL) -> MegaCloudVideo:
        video_id = embed_url.name or embed_url.parent.name
        # Explicitly use the unbound _get_client_key so we can call this method from other crawlers without inheritance
        client_key = await MegaCloudCrawler._get_client_key(self, embed_url)
        src_url = _V3_SOURCES_URL.with_query(id=video_id, _k=client_key)
        resp: dict[str, Any] = await self.request_json(src_url, headers=_HEADERS)

        if resp["encrypted"]:
            # TODO: Add logic to handle encrypted videos
            raise ScrapeError(403, "Video is encrypted")

        def parse_subs():
            counter = Counter()
            for track in resp["tracks"]:
                if track["kind"] != "captions":
                    continue

                url = self.parse_url(track["file"])
                label: str = track["label"]
                lang_code = _parse_lang_code(url.name, label)
                counter[lang_code] += 1
                if (count := counter[lang_code]) > 1:
                    suffix = f"{lang_code}.{count}{url.suffix}"
                else:
                    suffix = f"{lang_code}{url.suffix}"

                yield MegaCloudSubtitle(label, lang_code, suffix, url)

        return MegaCloudVideo(
            id=video_id,
            embed_url=embed_url.with_query(None),
            sources=tuple(self.parse_url(x["file"]) for x in resp["sources"]),
            subtitles=tuple(parse_subs()),
        )


_ISO639_MAP = {
    "arabic": "ara",
    "english": "eng",
    "french": "fre",
    "german": "ger",
    "italian": "ita",
    "portuguese": "por",
    "russian": "rus",
    "spanish": "spa",
    "chinese": "chi",
    "korean": "kor",
    "thai": "tha",
    "indonesian": "ind",
}


def _parse_lang_code(name: str, label: str) -> str:
    code = name.rsplit("-")[0]
    if len(code) in (2, 3):
        return code

    label = label.casefold()
    if code := _ISO639_MAP.get(label):
        return code

    for lang, code in _ISO639_MAP.items():
        if label.startswith(lang):
            return code

    return "unk"
