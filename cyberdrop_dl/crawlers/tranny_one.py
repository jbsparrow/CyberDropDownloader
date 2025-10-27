from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DownloadError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    VIDEO = "div#placeVideo div#videoContainer"
    TITLE = "span.movie-title-text"
    VIDEO_THUMBS = "div.thumbs-container a.pp"


_SELECTORS = Selectors()
PRIMARY_URL = AbsoluteHttpURL("https://tranny.one")


class TrannyOneCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/view/<video_id>",
        "Search": "/search/<search_query>",
    }
    DOMAIN: ClassVar[str] = "tranny.one"
    FOLDER_DOMAIN: ClassVar[str] = "Tranny.One"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    _RATE_LIMIT = 3, 10

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "view" in scrape_item.url.parts:
            return await self.video(scrape_item)
        elif "search" in scrape_item.url.parts:
            return await self.search(scrape_item)
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

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        MAX_VIDEO_COUNT_PER_PAGE: int = 52
        query = scrape_item.url.parts[-1]
        title = self.create_title(f"Search - {query}")
        scrape_item.setup_as_album(title)

        for page in itertools.count(1):
            page_url = scrape_item.url.with_query({"pageId" : page})
            soup = await self.request_soup(page_url)
            videos = list(css.iselect(soup, _SELECTORS.VIDEO_THUMBS))
            for video in  videos:
                video_url = self.parse_url(css.get_attr(video, "href"))
                new_scrape_item = scrape_item.create_child(video_url)
                self.create_task(self.run(new_scrape_item))
            if (len(videos) < MAX_VIDEO_COUNT_PER_PAGE):
                break


