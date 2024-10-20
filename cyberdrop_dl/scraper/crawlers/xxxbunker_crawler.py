from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeFailure
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper
from datetime import datetime, timedelta
from calendar import timegm
import re
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem

DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)

class XXXBunkerCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "xxxbunker", "XXXBunker")
        self.primary_base_domain = URL("https://xxxbunker.com")
        self.api_download = URL('https://xxxbunker.com/ajax/downloadpopup')
        self.request_limiter = AsyncLimiter(10, 1)

    
    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)

        # modify URL to always start on page 1
        new_parts = [part for part in scrape_item.url.parts[1:] if "page-" not in part]
        scrape_item.url = scrape_item.url.with_path("/".join(new_parts)).with_query(scrape_item.url.query)

        await self.video(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video"""
        if await self.check_complete_from_referer(scrape_item):
            return
        
        video_id = scrape_item.url.parts[1]
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url)
            video_iframe: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url.with_path(f"player/{video_id}"))

        title = soup.select_one('title').text.rsplit(" : XXXBunker.com")[0].strip()
        # WARNING: just for testing, needs to be removed on final implementation
        PHPSESSID = ''
        self.client.client_manager.cookies.update_cookies({"PHPSESSID": PHPSESSID},
                                                            response_url=self.primary_base_domain)
        try:
            src = video_iframe.select_one('source')
            src_url = URL(src.get('src'))
            relative_date_str = soup.select_one("div.video-details").find('li', string='Date Added').find_next('li').text.strip()
            date = await self.parse_relative_date(relative_date_str)
            scrape_item.possible_datetime = date
            internal_id = src_url.query.get('id')

            if 'internal' in src_url.parts:
                internal_id = video_id

            data = ({'internalid': internal_id })

            async with self.request_limiter:
                ajax_dict = await self.client.post_data(self.domain, self.api_download, data=data)
                ajax_soup = BeautifulSoup(ajax_dict['floater'], 'html.parser')
            
            link = URL(ajax_soup.select_one('a#download-download').get('href'))
 
        except AttributeError:
            if "This is a private" in soup.text:
                raise ScrapeFailure(403, f"Private video: {scrape_item.url}")
            raise ScrapeFailure(404, f"Could not find video source for {scrape_item.url}")
        
        # NOTE: hardcoding the extension to prevent quering the final server URL
        # final server URL is always different so it can not be saved to db.
        filename, ext = f"{video_id}.mp4" , '.mp4'
        
        # TODO: add custom filename param to handle_file 
        #custom_file_name, _ = await get_filename_and_ext(f"{title} [{filename}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext) #, custom_file_name)


    async def web_pager(self, url: URL) -> AsyncGenerator[BeautifulSoup]:
        "Generator of website pages"
        page_url = url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_BS4(self.domain, page_url)
            next_page = soup.select_one("div.page-list").find('a', string='next')
            yield soup
            if next_page :
                page_url = next_page.get('href')
                if page_url:
                    if page_url.startswith("/"):
                        page_url = self.primary_base_domain / page_url[1:]
                    page_url = URL(page_url)
                    continue
            break

    async def parse_relative_date(self, relative_date: timedelta|str) -> int:
        """Parses `datetime.timedelta` or `string` in a timedelta format. Returns `today() - parsed_timedelta` as an unix timestamp"""
        if isinstance(relative_date,str):
            time_str = relative_date.casefold()
            matches: list[str] = re.findall(DATE_PATTERN, time_str)

            # Assume today
            time_dict = {'days':0}

            for value, unit in matches:
                value = int(value)
                unit = unit.lower()
                time_dict[unit] = value

            relative_date = timedelta (**time_dict)

        date = datetime.today() - relative_date
        return timegm(date.timetuple())