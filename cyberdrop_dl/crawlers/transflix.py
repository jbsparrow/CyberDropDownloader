from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.mediaprops import Resolution
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    VIDEO = "video#player > source"
    SEARCH_VIDEOS = "div.list-videos div.item > a"
    NEXT_PAGE = "li.next"


_SELECTORS = Selectors()

TITLE_TRASH = "Free Trans Porn - TransFlix"
RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]
PRIMARY_URL = AbsoluteHttpURL("https://transflix.net")

class TransflixCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/video/...",
        "Search": "/search/?q=...",
    }
    DOMAIN: ClassVar[str] = "transflix"
    FOLDER_DOMAIN: ClassVar[str] = "TransFlix"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    _RATE_LIMIT = 3, 10

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "video" in scrape_item.url.parts:
            return await self.video(scrape_item)
        elif "search" in scrape_item.url.parts and (query := scrape_item.url.query.get("q")):
            return await self.search(scrape_item, query)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id: str = scrape_item.url.parts[-1].split("-")[-1]
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
        video = css.select_one(soup, _SELECTORS.VIDEO)
        video_url = self.parse_url(video["src"])
        title = css.select_one_get_text(soup, "title").replace(TITLE_TRASH, "").strip()
        res = _parse_resolution_from_title(title)
        filename, ext = self.get_filename_and_ext(video["src"])
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id, resolution=res)

        return await self.handle_file(
            video_url,
            scrape_item,
            filename,
            ext,
            custom_filename=custom_filename
        )

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        title = self.create_title(f"Search - {query}")
        scrape_item.setup_as_album(title)

        async for soup in self.web_pager(scrape_item.url, _SELECTORS.NEXT_PAGE):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.SEARCH_VIDEOS):
                self.create_task(self.run(new_scrape_item))


def _parse_resolution_from_title(title: str) -> str | None:
    for res in RESOLUTIONS:
        if res in title or res.replace("p", "") in title:
            return res
    return Resolution.unknown()
