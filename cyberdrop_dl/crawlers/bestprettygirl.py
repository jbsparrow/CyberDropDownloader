from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class Selectors:
    IMAGES = "div.elementor-widget-theme-post-content  div.elementor-widget-container img"
    VIDEO_IFRAME = "div.elementor-widget-theme-post-content  div.elementor-widget-container iframe"
    TITLE = "meta[property='og:title']"
    DATE = "meta[property='article:published_time']"
    COLLECTION_ITEM = "article.elementor-post.post a"


_SELECTORS = Selectors()

COLLECTION_PARTS = "category", "tag", "date"


class BestPrettyGirlCrawler(Crawler):
    primary_base_domain = URL("https://bestprettygirl.com/")
    next_page = "a.page-numbers.next"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "bestprettygirl.com", "BestPrettyGirl")
        self.request_limiter = AsyncLimiter(4, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        is_date = len(scrape_item.url.parts) > 3
        if any(p in scrape_item.url.parts for p in COLLECTION_PARTS) or is_date:
            return await self.collection(scrape_item)
        await self.gallery(scrape_item)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        collection_type = title = ""
        async for soup in self.web_pager(scrape_item.url):
            if not collection_type:
                title_tag = soup.select_one(_SELECTORS.TITLE)
                if not title_tag:
                    raise ScrapeError(422)

                for part in COLLECTION_PARTS:
                    if part in scrape_item.url.parts:
                        collection_type = part
                        break

                if not collection_type:
                    collection_type = "date"
                    date_parts = scrape_item.url.parts[1:4]
                    title = "-".join(date_parts)

                else:
                    title: str = title_tag.get_text(strip=True)  # type: ignore
                    title = title.removeprefix("Tag:").removeprefix("Category:").strip()
                    title = self.create_title(f"{title} [{collection_type}]")

                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.COLLECTION_ITEM):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        og_title: str = soup.select_one(_SELECTORS.TITLE)["content"]  # type: ignore
        date_str: str = soup.select_one(_SELECTORS.DATE)["content"]  # type: ignore
        title = self.create_title(og_title)
        scrape_item.setup_as_album(title)
        scrape_item.possible_datetime = self.parse_date(date_str)

        trash_split = "-0000-"
        trash_len: int = 0
        for _, link in self.iter_tags(soup, _SELECTORS.IMAGES, "src"):
            if not trash_len:
                trash_len = link.name.find(trash_split) + len(trash_split)
            filename, ext = self.get_filename_and_ext(link.name)
            custom_filename = link.name[trash_len:]
            custom_filename, _ = self.get_filename_and_ext(custom_filename)
            await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEO_IFRAME, "data-src"):
            new_scrape_item.url = new_scrape_item.url.with_host("vidply.com")
            self.handle_external_links(new_scrape_item)
