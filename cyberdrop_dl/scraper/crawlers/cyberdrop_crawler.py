from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem, FILE_HOST_ALBUM
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper
from cyberdrop_dl.clients.errors import ScrapeItemMaxChildrenReached

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class CyberdropCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "cyberdrop", "Cyberdrop")
        self.api_url = URL("https://api.cyberdrop.me/api/")
        self.primary_base_url = URL("https://cyberdrop.me/")
        self.request_limiter = AsyncLimiter(1.0, 2.0)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)

        if "a" in scrape_item.url.parts:
            scrape_item.url = scrape_item.url.with_query("nojs")
            await self.album(scrape_item)
        else:
            await self.file(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        async with self.request_limiter:
            soup = await self.client.get_BS4(self.domain, scrape_item.url)
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0
        
        try:
            scrape_item.children_limit = self.manager.config_manager.settings_data['Download_Options']['maximum_number_of_children'][scrape_item.type]
        except (IndexError, TypeError):
            pass

        title = await self.create_title(soup.select_one("h1[id=title]").text, scrape_item.url.parts[2], None)
        date = await self.parse_datetime(soup.select("p[class=title]")[-1].text)

        links = soup.select("div[class*=image-container] a[class=image]")
        for link in links:
            link = link.get('href')
            if link.startswith("/"):
                link = self.primary_base_url.with_path(link)
            link = URL(link)

            new_scrape_item = await self.create_scrape_item(scrape_item, link, title, True, None, date, add_parent = scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.children += 1
            if scrape_item.children_limit:
                if scrape_item.children >= scrape_item.children_limit:
                    raise ScrapeItemMaxChildrenReached(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file"""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            JSON_Resp = await self.client.get_json(self.domain,
                                                   self.api_url / "file" / "info" / scrape_item.url.path[3:])

        filename, ext = await get_filename_and_ext(JSON_Resp["name"])

        async with self.request_limiter:
            JSON_Resp = await self.client.get_json(self.domain,
                                                   self.api_url / "file" / "auth" / scrape_item.url.path[3:])

        link = URL(JSON_Resp['url'])
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def parse_datetime(self, date: str) -> int:
        """Parses a datetime string into a unix timestamp"""
        date = datetime.datetime.strptime(date, "%d.%m.%Y")
        return calendar.timegm(date.timetuple())
