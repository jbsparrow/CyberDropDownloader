from __future__ import annotations

import calendar
import contextlib
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class EHentaiCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "e-hentai", "E-Hentai")
        self.request_limiter = AsyncLimiter(10, 1)
        self.warnings_set = False

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "g" in scrape_item.url.parts:
            if not self.warnings_set:
                await self.set_no_warnings(scrape_item)
            await self.album(scrape_item)
        elif "s" in scrape_item.url.parts:
            await self.image(scrape_item)
        else:
            log(f"Scrape Failed: Unknown URL Path for {scrape_item.url}", 40)
            self.manager.progress_manager.scrape_stats_progress.add_failure("Unsupported Link")

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(soup.select_one("h1[id=gn]").get_text(), None, None)
        date = self.parse_datetime(soup.select_one("td[class=gdt2]").get_text())
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = (
                self.manager.config_manager.settings_data.download_options.maximum_number_of_children[scrape_item.type]
            )

        images = soup.select("div[class=gdtm] div a")
        for image in images:
            link = URL(image.get("href"))
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                link,
                title,
                True,
                None,
                date,
                add_parent=scrape_item.url,
            )
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

        next_page_opts = soup.select('td[onclick="document.location=this.firstChild.href"]')
        next_page = None
        for maybe_next in next_page_opts:
            if maybe_next.get_text() == ">":
                next_page = maybe_next.select_one("a")
                break
        if next_page is not None:
            next_page = URL(next_page.get("href"))
            if next_page is not None:
                new_scrape_item = self.create_scrape_item(scrape_item, next_page, "")
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        image = soup.select_one("img[id=img]")
        link = URL(image.get("src"))
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def set_no_warnings(self, scrape_item: ScrapeItem) -> None:
        """Sets the no warnings cookie."""
        self.warnings_set = True
        async with self.request_limiter:
            scrape_item.url = URL(str(scrape_item.url) + "/").update_query("nw=session")
            await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        if date.count(":") == 1:
            date = date + ":00"
        date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(date.timetuple())
