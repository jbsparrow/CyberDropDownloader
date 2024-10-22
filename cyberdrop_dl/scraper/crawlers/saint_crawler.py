from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL
import re

from cyberdrop_dl.clients.errors import ScrapeFailure
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from bs4 import BeautifulSoup
    from re import Match

class SaintCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "saint", "Saint")
        self.primary_base_domain = URL("https://saint2.su")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)

        if "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.video(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url)

        title_portion = soup.select_one('title').text.rsplit(" - Saint Video Hosting")[0].strip()
        if not title_portion:
            title_portion = scrape_item.url.name
        title = await self.create_title(title_portion, album_id , None)
        await scrape_item.add_to_parent_title(title)

        videos = soup.select('a.btn-primary.action.download')
       
        for video in videos:
            match: Match = re.search(r"\('(.+?)'\)", video.get('onclick'))
            link = URL(match.group(1)) if match else None
            filename, ext = await get_filename_and_ext(link.name)
            if not await self.check_album_results(link, results):
                await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video page"""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url)
        try:
            link = URL(soup.select_one('video[id=main-video] source').get('src'))
        except AttributeError:
            raise ScrapeFailure(404, f"Could not find video source for {scrape_item.url}")
        filename, ext = await get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
