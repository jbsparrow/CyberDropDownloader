from __future__ import annotations

from typing import TYPE_CHECKING
from aiolimiter import AsyncLimiter
from yarl import URL
from multidict import MultiDict

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
        scrape_item.url = await self.get_original_url(scrape_item)

        if await self.manager.real_debrid_manager.is_supported_folder(scrape_item.url):
            await self.folder(scrape_item)
        else:
            await self.file(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a folder"""
        original_url = scrape_item.url
        await log (f'scraping folder with RealDebrid: {original_url}',10)
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
        original_url = database_url = debrid_url = scrape_item.url
        password = original_url.query.get('password','')

        if await self.check_complete_from_referer(original_url):
            return
        
        self_hosted = await self.is_self_hosted(original_url)

        if not self_hosted:
            title = await self.create_title(f"files [{original_url.host.lower()}]", None, None)
            scrape_item.part_of_album = True
            await scrape_item.add_to_parent_title(title)
            async with self.request_limiter:
                debrid_url = await self.manager.real_debrid_manager.unrestrict_link(original_url, password)
        
        if await self.check_complete_from_referer(debrid_url):
            return
        
        await log(f'Real Debrid:\n  Original URL: {original_url}\n  Debrid URL: {debrid_url}',10)            

        if not self_hosted:
            # Some hosts use query params or fragment as id or password (ex: mega.nz)
            # This save the query and fragment as parts of the URL path since DB lookups only use url_path 
            database_url = self.primary_base_domain / original_url.host.lower() / original_url.path[1:]
            if original_url.query:
                query_params_list = [item for pair in original_url.query.items() for item in pair]
                database_url = database_url / 'query' / "/".join(query_params_list)

            if original_url.fragment:
                database_url = database_url / 'frag'/ original_url.fragment

        filename, ext = await get_filename_and_ext(debrid_url.name)
        await self.handle_file(database_url, scrape_item, filename, ext, debrid_link = debrid_url)

    async def is_self_hosted(self, url: URL):
        return any ({subdomain in url.host for subdomain in ('download.', 'my.')}) and self.domain in url.host

    async def get_original_url(self, scrape_item: ScrapeItem) -> URL:
        if await self.is_self_hosted(scrape_item.url):
            return scrape_item.url
        
        parts_dict = {'parts': [] , 'query': [], 'frag': []}
        key = 'parts'

        original_domain = scrape_item.url.parts[1]
        for part in scrape_item.url.parts[2:]:
            if part == 'query':
                key = part
                continue
            elif part == 'frag':
                key = part
                continue
            parts_dict[key].append(part)

        path = '/'.join(parts_dict['parts'])
        query = MultiDict()

        for i in range(0, parts_dict['query'], 2):
            query[parts_dict[i]] = parts_dict[i+1]

        frag = parts_dict['frag'] if parts_dict['frag'] else None

        original_url = URL(f'https://{original_domain}').with_path(path).with_query(query).with_fragment(frag)
        return original_url



