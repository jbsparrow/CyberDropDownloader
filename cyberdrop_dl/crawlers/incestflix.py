from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class Selectors:
    TITLE = "div#incflix-videowrap > h2"
    VIDEO = "div#incflix-videowrap source"
    NEXT = "table#incflix-pager a:contains('>')"
    VIDEO_THUMBS = "section#photos a"
    TAG_TITLE = "span#replaceTag1"


_SELECTORS = Selectors()


class IncestflixCrawler(Crawler):
    primary_base_domain = URL("https://www.incestflix.com")
    next_page_selector = _SELECTORS.NEXT

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "incestflix", "IncestFlix")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "watch" in scrape_item.url.parts:
            return await self.video(scrape_item)
        if "tag" in scrape_item.url.parts:
            return await self.tag(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        title: str = soup.select_one(_SELECTORS.TITLE).get_text(strip=True)
        video = soup.select_one(_SELECTORS.VIDEO)
        url = self.parse_url(video.get("src"))
        filename, ext = self.get_filename_and_ext(f"{title}.mp4")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=url)

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        title_created: bool = False
        async for soup in self.web_pager(scrape_item.url):
            if not title_created:
                title = self.create_title(soup.select_one(_SELECTORS.TAG_TITLE).get_text(strip=True))
                scrape_item.setup_as_album(title)
                title_created = True
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEO_THUMBS):
                self.manager.task_group.create_task(self.run(new_scrape_item))
