from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://xgroovy.com")
PICTURES_DOMAIN = "photos.xgroovy.com"


class Selectors:
    VIDEO = "video#main_video"
    GIF = "div.gif-video-wrapper > video"
    UPLOAD_DATE = "script:-soup-contains('uploadDate')"
    PORNSTAR_NAME = "h2.object-title"
    SEARCH_VIDEOS = "div.list-videos a.popito"
    NEXT_PAGE = "div.pagination-holder li.next > a"


_SELECTORS = Selectors()


class Format(NamedTuple):
    resolution: str
    link_str: str


class CollectionType(StrEnum):
    CATEGORIES = "categories"
    CHANNELS = "channels"
    PORNSTARS = "pornstars"
    SEARCH = "search"
    TAG = "tag"


class XGroovyCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": ("/shemale/videos/<video_id>/...", "/videos/<video_id>/..."),
        "Gif": ("/shemale/gifs/<gif_id>/...", "/gifs/<gif_id>/..."),
        "Search": ("/shemale/search/...", "/search/..."),
        "Pornstar": ("/shemale/pornstars/<pornstar_id>/...", "/pornstars/<pornstar_id>/..."),
        "Tag": ("/shemale/tags/...", "/tags/..."),
        "Channel": ("/shemale/channels/...", "/channels/..."),
    }
    DOMAIN: ClassVar[str] = "xgroovy"
    FOLDER_DOMAIN: ClassVar[str] = "XGroovy"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    _COLLECTION_TYPES = tuple(item.value for item in CollectionType)
    _RATE_LIMIT = 3, 10

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        elif "gifs" in scrape_item.url.parts:
            return await self.gif(scrape_item)
        elif scrape_item.url.host == PICTURES_DOMAIN:
            return await self.direct_file(scrape_item)
        elif collection_type := next((p for p in self._COLLECTION_TYPES if p in scrape_item.url.parts), None):
            return await self.collection(scrape_item, collection_type)
        raise ValueError

    @error_handling_wrapper
    async def gif(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        gif_id: str = scrape_item.url.parts[scrape_item.url.parts.index("gifs") + 1]
        soup = await self.request_soup(scrape_item.url)
        link = self.parse_url(css.get_attr(css.select_one(soup, _SELECTORS.GIF), "src"))
        return await self.download_video(scrape_item, gif_id, soup, link)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        video_id: str = scrape_item.url.parts[scrape_item.url.parts.index("videos") + 1]
        soup = await self.request_soup(scrape_item.url)
        best_format: Format = _get_best_format(css.select_one(soup, _SELECTORS.VIDEO))
        return await self.download_video(
            scrape_item, video_id, soup, self.parse_url(best_format.link_str), resolution=best_format.resolution
        )

    async def download_video(
        self,
        scrape_item: ScrapeItem,
        file_id: str,
        soup: BeautifulSoup,
        link: AbsoluteHttpURL,
        resolution: str | None = None,
    ):
        filename, ext = self.get_filename_and_ext(link.name)
        title = open_graph.get_title(soup)
        context = json.loads(css.select_one_get_text(soup, _SELECTORS.UPLOAD_DATE))
        scrape_item.possible_datetime = self.parse_iso_date(context.get("uploadDate"))
        custom_filename = self.create_custom_filename(title, ext, file_id=file_id, resolution=resolution)
        return await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: CollectionType) -> None:
        title = scrape_item.url.parts[-1]
        if collection_type == CollectionType.PORNSTARS:
            soup = await self.request_soup(scrape_item.url)
            title = css.select_one_get_text(soup, _SELECTORS.PORNSTAR_NAME)

        title = self.create_title(f"{title} - [{collection_type}]")
        scrape_item.setup_as_album(title)
        async for soup in self.web_pager(scrape_item.url, _SELECTORS.NEXT_PAGE):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.SEARCH_VIDEOS):
                self.create_task(self.run(new_scrape_item))


def _get_best_format(video_tag):
    options = []
    for src in video_tag.find_all("source"):
        url = src.get("src")
        title = src.get("title", "0p")
        resolution = int(title.replace("p", ""))
        options.append((resolution, url, title))
    best = max(options, key=lambda x: x[0])
    return Format(best[2], best[1])
