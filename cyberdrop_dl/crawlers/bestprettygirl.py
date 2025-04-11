from __future__ import annotations

import calendar
from datetime import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


IMAGES_SELECTOR = "div.elementor-widget-theme-post-content  div.elementor-widget-container img"
VIDEO_IFRAME_SELECTOR = "div.elementor-widget-theme-post-content  div.elementor-widget-container iframe"
TITLE_SELECTOR = "meta[property='og:title']"
DATE_SELECTOR = "meta[property='article:published_time']"
COLLECTION_PARTS = "category", "tag", "date"
ITEM_SELECTOR = "article.elementor-post.post a"


class BestPrettyGirlCrawler(Crawler):
    primary_base_domain = URL("https://bestprettygirl.com/")
    next_page_selector = "a.page-numbers.next"

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
                title_tag = soup.select_one(TITLE_SELECTOR)
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
                    title = title + f" [{collection_type}]"
                    title = self.create_title(title)

                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, ITEM_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        og_title: str = soup.select_one(TITLE_SELECTOR).get("content")  # type: ignore
        date_str: str = soup.select_one(DATE_SELECTOR).get("content")  # type: ignore
        date = datetime.fromisoformat(date_str)
        title = self.create_title(og_title)
        scrape_item.setup_as_album(title)
        scrape_item.possible_datetime = calendar.timegm(date.timetuple())

        trash: str = ""
        for _, link in self.iter_tags(soup, IMAGES_SELECTOR, "src"):
            if not trash:
                trash = link.name.split("-0000", 1)[0]
            filename, ext = self.get_filename_and_ext(link.name)
            custom_filename = link.name.replace(trash, "").removeprefix("-")
            custom_filename, _ = self.get_filename_and_ext(custom_filename)
            await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

        for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEO_IFRAME_SELECTOR, "data-src"):
            new_scrape_item.url = new_scrape_item.url.with_host("vidply.com")
            self.handle_external_links(new_scrape_item)
