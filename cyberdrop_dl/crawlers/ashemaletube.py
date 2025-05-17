from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class Selectors:
    PROFILE_VIDEOS = "div.sub-content div.media-item__inner > a[data-video-preview]"
    SEARCH_VIDEOS = "div.main-content div.media-item__inner > a[data-video-preview]"
    USER_NAME = "h1.username"
    PLAYLIST_VIDEOS = "a.playlist-video-item__thumbnail"
    VIDEO_PROPS_JS = "script:contains('uploadDate')"
    JS_PLAYER = "script:contains('var player = new VideoPlayer')"
    LOGIN_REQUIRED = "div.loginLinks:contains('To watch this video please')"
    IMAGE_ITEM = "div.imgItem"
    ALBUM_IMAGES = "div.gallery-detail div.thumb"
    ALBUM_TITLE = "div.prepositions-wrapper h1"
    GALLERY_ALBUM = "div.profile-content div.galItem > a"
    NEXT_PAGE = "a.rightKey"


_SELECTORS = Selectors()
RESOLUTIONS = ["2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
INCLUDE_VIDEO_ID_IN_FILENAME = True


class Format(NamedTuple):
    resolution: str
    link_str: str


class CollectionType(StrEnum):
    ALBUM = "album"
    MODEL = "model"
    PLAYLIST = "playlist"
    SEARCH = "search"
    PROFILE = "profile"


MEDIA_SELECTOR_MAP = {
    CollectionType.ALBUM: _SELECTORS.ALBUM_IMAGES,
    CollectionType.MODEL: _SELECTORS.PROFILE_VIDEOS,
    CollectionType.PLAYLIST: _SELECTORS.PLAYLIST_VIDEOS,
    CollectionType.SEARCH: _SELECTORS.SEARCH_VIDEOS,
    CollectionType.PROFILE: _SELECTORS.ALBUM_IMAGES,
}

TITLE_SELECTOR_MAP = {
    CollectionType.ALBUM: _SELECTORS.ALBUM_TITLE,
    CollectionType.MODEL: _SELECTORS.USER_NAME,
    CollectionType.PLAYLIST: "h1",
    CollectionType.SEARCH: "h1",
    CollectionType.PROFILE: _SELECTORS.USER_NAME,
}

TITLE_TRASH = "Shemale Porn Videos - Trending"


class AShemaleTubeCrawler(Crawler):
    primary_base_domain = URL("https://www.ashemaletube.com")
    next_page_selector = _SELECTORS.NEXT_PAGE

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "ashemaletube", "aShemaleTube")
        self.request_limiter = AsyncLimiter(3, 10)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p in scrape_item.url.parts for p in ("creators", "profiles", "pornstars", "model")):
            if "galleries" in scrape_item.url.parts:
                return await self.gallery(scrape_item)
            return await self.collection(scrape_item, CollectionType.MODEL)
        if "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        if "playlists" in scrape_item.url.parts:
            return await self.collection(scrape_item, CollectionType.PLAYLIST)
        if "search" in scrape_item.url.parts:
            return await self.collection(scrape_item, CollectionType.SEARCH)
        if "pics" in scrape_item.url.parts:
            if len(scrape_item.url.parts) >= 5:
                return await self.image(scrape_item)
            return await self.album(scrape_item)
        if "cam" in scrape_item.url.parts:
            raise ValueError
        raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        async for soup in self.web_pager(scrape_item.url, cffi=True):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.GALLERY_ALBUM):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        album_title = ""
        async for soup in self.web_pager(scrape_item.url, cffi=True):
            if not album_title:
                album_title = self.create_collection_title(soup, CollectionType.ALBUM)
                scrape_item.setup_as_album(album_title)

            for thumb in soup.select(MEDIA_SELECTOR_MAP[CollectionType.ALBUM]):
                await self.proccess_image(scrape_item, thumb)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: CollectionType) -> None:
        collection_title = ""
        async for soup in self.web_pager(scrape_item.url, cffi=True):
            if not collection_title:
                collection_title = self.create_collection_title(soup, collection_type)
                if collection_type == CollectionType.MODEL:
                    scrape_item.setup_as_profile(collection_title)
                else:
                    scrape_item.setup_as_album(collection_title)
            for _, new_scrape_item in self.iter_children(scrape_item, soup, MEDIA_SELECTOR_MAP[collection_type]):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    def create_collection_title(self, soup: BeautifulSoup, collection_type: CollectionType):
        title_elem = soup.select_one(TITLE_SELECTOR_MAP[collection_type])
        if not title_elem:
            raise ScrapeError(401)
        collection_title: str = title_elem.get_text(strip=True)  # type: ignore
        collection_title = collection_title.replace(TITLE_TRASH, "").strip()
        collection_title = self.create_title(f"{collection_title} [{collection_type}]")
        return collection_title

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)
        img_item = soup.select_one(_SELECTORS.IMAGE_ITEM)
        if not img_item:
            raise ScrapeError(404)
        await self.proccess_image(scrape_item, img_item)

    @error_handling_wrapper
    async def proccess_image(self, scrape_item: ScrapeItem, img_tag: Tag) -> None:
        if image := img_tag.select_one("img"):
            link_str: str = image["src"]  # type: ignore
        else:
            style: str = img_tag.select_one("a")["style"]  # type: ignore
            link_str = get_text_between(style, "url('", "');")
        url = self.parse_url(link_str).with_query(None)
        filename, ext = self.get_filename_and_ext(url.name)
        custom_filename, _ = self.get_filename_and_ext(f"{img_tag['data-image-id']}{ext}")
        await self.handle_file(url, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id: str = scrape_item.url.parts[2]
        canonical_url = self.primary_base_domain / "videos" / video_id
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)

        if soup.select_one(_SELECTORS.LOGIN_REQUIRED):
            raise ScrapeError(401)
        player = soup.select_one(_SELECTORS.JS_PLAYER)
        if not player:
            raise ScrapeError(422)
        is_hls, best_format = parse_player_info(player.text)
        if is_hls:
            raise ScrapeError(422)

        if video_object := soup.select_one(_SELECTORS.VIDEO_PROPS_JS):
            json_data = json.loads(video_object.text.strip())
            if "uploadDate" in json_data:
                scrape_item.possible_datetime = self.parse_date(json_data["uploadDate"])

        title: str = soup.select_one("title").text.split("- aShemaletube.com")[0].strip()  # type: ignore
        link = self.parse_url(best_format.link_str)

        scrape_item.url = canonical_url
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".mp4")
        include_id = f"[{video_id}]" if INCLUDE_VIDEO_ID_IN_FILENAME else ""
        custom_filename, _ = self.get_filename_and_ext(f"{title} {include_id}[{best_format.resolution}]{ext}")
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
        )


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_best_quality(info_dict: dict) -> Format:
    """Returns best available format"""
    active_url: str = ""
    active_res: str = ""
    for res in RESOLUTIONS:
        for item in info_dict:
            if item["active"] == "true":
                active_url = item["src"]
                active_res = item["desc"]
            if res == item["desc"]:
                return Format(res, item["src"])

    return Format(active_res, active_url)


def parse_player_info(script_text: str) -> tuple[bool, Format]:
    if match := re.search(r"hls:\s+(true|false)", script_text):
        is_hls = match.group(1) == "true"
        urls_info = "[{" + get_text_between(script_text, "[{", "}],") + "}]"
        format: Format = get_best_quality(json.loads(urls_info))
        return is_hls, format
    raise ScrapeError(404)
