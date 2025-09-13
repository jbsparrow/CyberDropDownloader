from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING, Any, ClassVar, Final

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures import AbsoluteHttpURL, Resolution
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper, filter_query, parse_url

if TYPE_CHECKING:
    from collections.abc import Sequence

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_PER_PAGE: int = 1000


@dataclasses.dataclass(slots=True)
class KVSVideo:
    id: str
    title: str
    url: AbsoluteHttpURL
    resolution: Resolution


class Selector:
    UNAUTHORIZED = "div.video-holder:contains('This video is a private video')"
    VIDEO_VARS = "script:contains('video_title:')"
    VIDEOS = "div#list_videos_common_videos_list_items a"
    MODEL_NAME = "div.pb-model-title .model-name"
    ITEM = "a[href].pb-item-link"
    ALBUM_TAB = "a.pb-heading-h2[href*='/albums/models/']"
    ALBUM_TITLE = ".pb-view-album-title h1"


def _pagination_query(url: AbsoluteHttpURL) -> dict[str, Any]:
    per_page_params = {
        "albums_per_page" if "albums" in url.parts else "videos_per_page": _PER_PAGE,
    }
    return filter_query(url.update_query(per_page_params).query, ("sort_by", "post_date"), "duration")


class PimpBunnyCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Videos": "/videos/...",
    }

    DOMAIN: ClassVar[str] = "pimpbunny.com"
    FOLDER_DOMAIN: ClassVar[str] = "PimpBunny"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://pimpbunny.com")
    DEFAULT_TRIM_URLS: Final = False
    NEXT_PAGE_SELECTOR: Final = ".pb-pagination-list .next a[href]"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["videos", _, *_]:
                return await self.video(scrape_item)
            case ["onlyfans-models", model_name, *_]:
                return await self.model(scrape_item, model_name)
            case ["albums", "models", model_name, *_]:
                return await self.model_albums(scrape_item, model_name)
            case ["albums", name, *_]:
                return await self.album(scrape_item, name)
            case ["categories" as type_, name, *_]:
                return await self.collection(scrape_item, type_, name)
            case ["tags" as type_, name, *_]:
                return await self.collection(scrape_item, type_, name)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: str, slug: str) -> None:
        url = scrape_item.url.origin() / collection_type / slug / ""
        title = self.create_title(f"{slug} [{collection_type}]")
        scrape_item.setup_as_album(title)

        query = _pagination_query(scrape_item.url)
        async for soup in self.web_pager(url.with_query(query)):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem, model_name: str) -> None:
        model_url = scrape_item.url.origin() / "onlyfans-models" / model_name / ""
        name: str = ""

        query = _pagination_query(scrape_item.url)
        async for soup in self.web_pager(model_url.with_query(query)):
            if not name:
                name = css.select_one_get_text(soup, Selector.MODEL_NAME)
                scrape_item.setup_as_profile(self.create_title(f"{name} [model]"))

            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(new_scrape_item))

        has_albums = soup.select_one(Selector.ALBUM_TAB)
        if has_albums:
            await self.model_albums(scrape_item, model_name)

    @error_handling_wrapper
    async def model_albums(self, scrape_item: ScrapeItem, model_name: str) -> None:
        albums_url = scrape_item.url.origin() / "albums/models" / model_name / ""
        name: str = ""

        query = _pagination_query(scrape_item.url)
        async for soup in self.web_pager(albums_url.with_query(query)):
            if not name:
                name = css.select_one_get_text(soup, Selector.MODEL_NAME)
                if name not in scrape_item.parent_title:
                    scrape_item.setup_as_profile(self.create_title(f"{name} [model]"))

            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
        video = self.extract_kvs_video(soup)
        custom_filename = self.create_custom_filename(
            video.title, video.url.suffix, file_id=video.id, resolution=video.resolution
        )
        scrape_item.possible_datetime = self.parse_iso_date(css.get_json_ld_date(soup))
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            video.url.name,
            video.url.suffix,
            custom_filename=custom_filename,
            debrid_link=video.url,
        )

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, name: str) -> None:
        album_url = scrape_item.url.origin() / "albums" / name / ""
        title: str = ""
        async for soup in self.web_pager(album_url):
            if not title:
                title = css.select_one_get_text(soup, Selector.ALBUM_TITLE)
                scrape_item.setup_as_album(self.create_title(f"{title} [album]"))

            for _, image in self.iter_tags(soup, Selector.ITEM):
                self.create_task(self.direct_file(scrape_item, image))
                scrape_item.add_children()

    @classmethod
    def extract_kvs_video(cls, soup: BeautifulSoup) -> KVSVideo:
        if soup.select_one(Selector.UNAUTHORIZED):
            raise ScrapeError(401, "Private video")

        script = css.select_one_get_text(soup, Selector.VIDEO_VARS)
        video = _parse_video_vars(script)
        if not video.title:
            title = open_graph.get_title(soup) or css.page_title(soup)
            assert title
            video.title = css.sanitize_page_title(title, cls.DOMAIN)
        return video


_HASH_LENGTH = 32
_match_video_url_keys = re.compile(r"^video_(?:url|alt_url\d*)$").match
_find_flashvars = re.compile(r"(\w+):\s*'([^']*)'").findall


def _parse_video_vars(video_vars: str) -> KVSVideo:
    flashvars: dict[str, str] = dict(_find_flashvars(video_vars))
    url_keys = filter(_match_video_url_keys, flashvars.keys())
    license_token = _get_license_token(flashvars["license_code"])

    def get_formats():
        for key in url_keys:
            url_str = flashvars[key]
            if "/get_file/" not in url_str:
                continue
            resolution = Resolution.parse(flashvars[f"{key}_text"])
            url = _deobfuscate_url(url_str, license_token)
            yield resolution, url

    resolution, url = max(get_formats())
    return KVSVideo(flashvars["video_id"], flashvars["video_title"], url, resolution)


def _deobfuscate_url(video_url_str: str, license_token: Sequence[int]) -> AbsoluteHttpURL:
    raw_url_str = video_url_str.removeprefix("function/0/")
    url = parse_url(raw_url_str)
    is_obfuscated = raw_url_str != video_url_str
    if not is_obfuscated:
        return url

    hash, tail = url.parts[3][:_HASH_LENGTH], url.parts[3][_HASH_LENGTH:]
    indices = list(range(_HASH_LENGTH))

    # Swap indices of hash according to the destination calculated from the license token
    accum = 0
    for src in reversed(range(_HASH_LENGTH)):
        accum += license_token[src]
        dest = (src + accum) % _HASH_LENGTH
        indices[src], indices[dest] = indices[dest], indices[src]

    new_parts = list(url.parts)
    new_parts[3] = "".join(hash[index] for index in indices) + tail
    return url.with_path("/".join(new_parts[1:]), keep_query=True, keep_fragment=True)


def _get_license_token(license_code: str) -> tuple[int, ...]:
    license_code = license_code.removeprefix("$")
    license_values = [int(char) for char in license_code]
    modlicense = license_code.replace("0", "1")
    middle = len(modlicense) // 2
    fronthalf = int(modlicense[: middle + 1])
    backhalf = int(modlicense[middle:])
    modlicense = str(4 * abs(fronthalf - backhalf))[: middle + 1]

    return tuple(
        (license_values[index + offset] + current) % 10
        for index, current in enumerate(map(int, modlicense))
        for offset in range(4)
    )
