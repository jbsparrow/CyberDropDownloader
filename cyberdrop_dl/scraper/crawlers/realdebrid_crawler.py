from __future__ import annotations

from typing import TYPE_CHECKING
from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper, log
from cyberdrop_dl.managers.realdebrid_manager import RATE_LIMIT

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

class RealDebridCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "real-debrid", "RealDebrid")
        self.headers = {}
        self.primary_base_domain = URL('https://real-debrid.com')
        self.request_limiter = AsyncLimiter(RATE_LIMIT, 60)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)

        if await self.manager.real_debrid_manager.is_supported_folder(scrape_item.url):
            await self.folder(scrape_item)
        else:
            await self.file(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a folder"""
        await log ('scraping folder with RealDebrid',10)
        original_url = scrape_item.url
        folder_id = await self.manager.real_debrid_manager.guess_folder(original_url)
        scrape_item.album_id = folder_id
        scrape_item.part_of_album = True

        title = await self.create_title(f"{folder_id} [{original_url.host.lower()}]", None, None)
        await scrape_item.add_to_parent_title(title)

        async with self.request_limiter:
            links = await self.manager.real_debrid_manager.unrestrict_folder(original_url)

        for link in links:
            new_scrape_item = await self.create_scrape_item(scrape_item, link, "", True, folder_id , add_parent = original_url )
            await self.file(new_scrape_item)
        
                
    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file"""
        await log ('scraping file with RealDebrid',10)
        original_url = scrape_item.url
        password = original_url.query.get('password','')
        async with self.request_limiter:
            debrid_link = await self.manager.real_debrid_manager.unrestrict_link(original_url, password)

        await log (f"{debrid_link=}",10)
        
        if await self.check_complete_from_referer(scrape_item):
            return

        if not scrape_item.part_of_album:
            title = await self.create_title(f"files [{original_url.host.lower()}]", None, None)
            await scrape_item.add_to_parent_title(title)

        link = self.primary_base_domain / original_url.host.lower() / original_url.path[1:] / debrid_link.name
        link = scrape_item.url.with_query(original_url.query).with_fragment(original_url.fragment.split('/')[0])
        await log (f"{link=}",10)
        filename, ext = await get_filename_and_ext(debrid_link.name)
        await self.handle_file(link, scrape_item, filename, ext, debrid_link)


