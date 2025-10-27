from __future__ import annotations

import itertools
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    VIDEO = "div#placeVideo div#videoContainer"
    TITLE = "span.movie-title-text"
    VIDEO_THUMBS = "div.thumbs-container a.pp"
    MODEL_NAME = "h1.ps-heading-name"
    ALBUM_TITLE = "h1.top"
    ALBUM_THUMBS = "div.pic-list a"


_SELECTORS = Selectors()

class CollectionType(StrEnum):
    ALBUM = "album"
    MODEL = "model"
    SEARCH = "search"

TITLE_SELECTOR_MAP = {
    CollectionType.MODEL: _SELECTORS.MODEL_NAME,
    CollectionType.ALBUM: _SELECTORS.ALBUM_TITLE,
    CollectionType.SEARCH: None,
}

PRIMARY_URL = AbsoluteHttpURL("https://tranny.one")
PICTURES_DOMAIN = "pics.tranny.one"


class TrannyOneCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/view/<video_id>",
        "Search": "/search/<search_query>",
        "Pornstars": "/pornstar/<model_id>/<model_name>",
        "Album" : "/pics/album/<album_id>"
    }
    DOMAIN: ClassVar[str] = "tranny.one"
    FOLDER_DOMAIN: ClassVar[str] = "Tranny.One"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    _RATE_LIMIT = 3, 10

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "view" in scrape_item.url.parts:
            return await self.video(scrape_item)
        elif "search" in scrape_item.url.parts:
            return await self.collection(scrape_item, CollectionType.SEARCH)
        elif "pornstars" in scrape_item.url.parts:
            return await self.collection(scrape_item, CollectionType.MODEL)
        elif scrape_item.url.host == PICTURES_DOMAIN:
            return await self.direct_file(scrape_item)
        elif "album" in scrape_item.url.parts:
            return await self.album(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id: str = scrape_item.url.parts[-1]
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
        title = css.select_one_get_text(soup, _SELECTORS.TITLE)
        video = css.select_one(soup, _SELECTORS.VIDEO)
        link = self.parse_url(css.get_attr(video, "data-high"))
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id)

        return await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    def create_collection_title(self, soup: BeautifulSoup, url: AbsoluteHttpURL, collection_type: CollectionType) -> str:
        collection_title: str = ""
        if collection_type == CollectionType.SEARCH:
            collection_title = url.parts[-1]
        else:
            title_elem = soup.select_one(TITLE_SELECTOR_MAP[collection_type])
            if not title_elem:
                raise ScrapeError(401)
            collection_title: str = title_elem.get_text(strip=True)
        collection_title = self.create_title(f"{collection_title} [{collection_type}]")
        return collection_title

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: CollectionType) -> None:
        MAX_VIDEO_COUNT_PER_PAGE: int = 52
        title_created: bool = False
        for page in itertools.count(1):
            page_url = scrape_item.url.with_query({"pageId" : page})
            soup = await self.request_soup(page_url)

            if not title_created:
                title = self.create_collection_title(soup, scrape_item.url, collection_type)
                scrape_item.setup_as_album(title)
                title_created = True

            videos = list(css.iselect(soup, _SELECTORS.VIDEO_THUMBS))
            for video in  videos:
                video_url = self.parse_url(css.get_attr(video, "href"))
                new_scrape_item = scrape_item.create_child(video_url)
                self.create_task(self.run(new_scrape_item))

            if (len(videos) < MAX_VIDEO_COUNT_PER_PAGE):
                break

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        album_title = ""
        album_id: str = scrape_item.url.parts[-1]
        soup = await self.request_soup(scrape_item.url)
        for pic in css.iselect(soup, _SELECTORS.ALBUM_THUMBS):
            if not album_title:
                album_title = self.create_collection_title(soup, scrape_item.url, CollectionType.ALBUM)
                scrape_item.setup_as_album(album_title, album_id=album_id)
            pic_url = self.parse_url(css.get_attr(pic, "href"))
            new_scrape_item = scrape_item.create_child(pic_url)
            self.create_task(self.run(new_scrape_item))
