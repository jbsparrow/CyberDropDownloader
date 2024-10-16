from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeFailure
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import log, get_filename_and_ext, error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from bs4 import BeautifulSoup


class TokioMotionCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "tokyomotion", "Tokyomotion")
        self.primary_base_domain = URL("https://www.tokyomotion.net")
        self.request_limiter = AsyncLimiter(10, 1)
        self.page_selector = 'a.prevnext'
        self.title_selector = 'meta[property="og:title"]'

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)

        if 'video' in scrape_item.url.parts:
            await self.video(scrape_item)

        elif 'videos' in scrape_item.url.parts:
            await self.playlist(scrape_item)

        elif 'photo' in scrape_item.url.parts:
            await self.photo(scrape_item)

        elif any(part in scrape_item.url.parts for part in ('albums','photos')):
            await self.album(scrape_item)

        elif 'user' in scrape_item.url.parts:
            await self.profile(scrape_item)

        else:
            await self.search(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an video"""
        if await self.check_complete_from_referer(scrape_item):
            return
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url)
        try:
            srcSD = soup.select_one('source[title="SD"]')
            srcHD = soup.select_one('source[title="HD"]')
            src = (srcHD or srcSD).get('src')
            link = URL(src)
        except AttributeError as e:
            raise ScrapeFailure(404, f"Could not find video source for {scrape_item.url}")
        
        title = soup.select_one('title').text.rsplit(" - TOKYO Motion")[0].strip()
       
        # NOTE: hardcoding the extension to prevent quering the final server URL
        # final server URL is always diferent so it can not be saved to db.
        filename, ext = scrape_item.url.parts[2], '.mp4'
        custom_file_name, _ = await get_filename_and_ext(title + ext)
        await self.handle_file(link, scrape_item, filename, ext, custom_file_name)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        raise NotImplementedError
    
    @error_handling_wrapper
    async def photo(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        raise NotImplementedError
    
    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        raise NotImplementedError
    
    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        raise NotImplementedError
    
    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        raise NotImplementedError
