from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class Rule34XXXCrawler(Crawler):
    primary_base_domain = URL("https://rule34.xxx")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34.xxx", "Rule34XXX")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        await self.set_cookies()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        if "tags" in scrape_item.url.query_string:
            await self.tag(scrape_item)
        elif "id" in scrape_item.url.query_string:
            await self.file(scrape_item)
        else:
            log(f"Scrape Failed: Unknown URL Path for {scrape_item.url}", 40)
            self.manager.progress_manager.scrape_stats_progress.add_failure("Unsupported Link")

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        title_portion = scrape_item.url.query["tags"].strip()
        title = self.create_title(title_portion)
        scrape_item.part_of_album = True

        content = soup.select("div[class=image-list] span a")
        for file_page in content:
            link_str: str = file_page.get("href")
            encoded = "%" in link_str
            if link_str.startswith("/"):
                link = self.primary_base_domain.joinpath(link_str[1:], encoded=encoded)
            link = URL(link_str, encoded=encoded)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, True, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

        next_page = soup.select_one("a[alt=next]")
        if next_page:
            next_page_str: str = next_page.get("href")
            next_page = (
                scrape_item.url.with_query(next_page_str[1:])
                if next_page_str.startswith("?")
                else URL(next_page_str, encoded="%" in next_page)
            )
            new_scrape_item = self.create_scrape_item(scrape_item, next_page)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        image = soup.select_one("img[id=image]")
        if image:
            link_str: str = image.get("src")
            link = URL(link_str, encoded="%" in link_str)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
        video = soup.select_one("video source")
        if video:
            link_str: str = video.get("src")
            link = URL(link_str, encoded="%" in link_str)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def set_cookies(self) -> None:
        """Sets the cookies for the client."""
        self.client.client_manager.cookies.update_cookies(
            {"resize-original": "1"}, response_url=self.primary_base_domain
        )
