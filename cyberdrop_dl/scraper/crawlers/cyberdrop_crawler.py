from __future__ import annotations

import calendar
import datetime
import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
import aiofiles
from yarl import URL
from bs4 import BeautifulSoup

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem, FILE_HOST_ALBUM
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper, log
from cyberdrop_dl.clients.errors import ScrapeFailure, DDOSGuardFailure
from cyberdrop_dl.clients.errors import ScrapeItemMaxChildrenReached

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from bs4 import BeautifulSoup

CDN_POSSIBILITIES = re.compile(
    r"^(?:(?:k1)[0-9]{0,2})(?:redir)?\.cyberdrop?\.[a-z]{2,3}$")

class CyberdropCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "cyberdrop", "Cyberdrop")
        self.api_url = URL("https://api.cyberdrop.me/api/")
        self.primary_base_domain = URL("https://cyberdrop.me/")
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
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url, origin=scrape_item)
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0
        
        try:
            scrape_item.children_limit = self.manager.config_manager.settings_data['Download_Options']['maximum_number_of_children'][scrape_item.type]
        except (IndexError, TypeError):
            pass

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True
        date = title = None

        try:
            title = await self.create_title(soup.select_one("h1[id=title]").text, scrape_item.album_id, None)
        except AttributeError:
            raise ScrapeFailure (404, message = 'No album information found in response content', origin = scrape_item)

        date = soup.select("p[class=title]")
        if date:
            date = await self.parse_datetime(date[-1].text)

        links = soup.select("div[class*=image-container] a[class=image]")
        for link in links:
            link = link.get('href')
            if link.startswith("/"):
                link = self.primary_base_domain.with_path(link)
            link = URL(link)

            new_scrape_item = await self.create_scrape_item(scrape_item, link, title, True, None, date,
                                                            add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.children += 1
            if scrape_item.children_limit:
                if scrape_item.children >= scrape_item.children_limit:
                    raise ScrapeItemMaxChildrenReached(origin = scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file"""
        scrape_item.url = await self.get_stream_link(scrape_item.url)

        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            JSON_Resp = await self.client.get_json(self.domain,
                                                self.api_url / "file" / "info" / scrape_item.url.path[3:],
                                                origin=scrape_item)

        filename, ext = await get_filename_and_ext(JSON_Resp["name"])

        async with self.request_limiter:
            JSON_Resp = await self.client.get_json(self.domain,
                                                self.api_url / "file" / "auth" / scrape_item.url.path[3:],
                                                origin=scrape_item)

        link = URL(JSON_Resp['url'])
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_stream_link(self, url: URL) -> URL:
        """Gets the stream link for a given URL
        
        NOTE: This makes a request to get the final URL (if necessary). Calling function must use `@error_handling_wrapper`
        
        """
        
        if any([part in url.parts for part in ('a','f')]):
            return url
        
        if self.is_cdn(url):
            return self.primary_base_domain / "f" / url.parts[-1]
            
        _ , streaming_url = await self.client.get_BS4_and_return_URL(self.domain, url)
    
        return streaming_url

    @staticmethod
    def is_cdn(url: URL) -> bool:
        """Checks if a given URL is from a CDN"""
        return bool(re.match(CDN_POSSIBILITIES, url.host))

    @staticmethod
    async def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp"""
        date = datetime.datetime.strptime(date, "%d.%m.%Y")
        return calendar.timegm(date.timetuple())
