from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem, FILE_HOST_PROFILE, FILE_HOST_ALBUM
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper, log
from cyberdrop_dl.clients.errors import ScrapeItemMaxChildrenReached

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class EromeCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "erome", "Erome")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)

        if "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.profile(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile"""
        self.type = FILE_HOST_PROFILE
        scrape_item.children = scrape_item.children_limit = 0
        async with self.request_limiter:
            soup = await self.client.get_BS4(self.domain, scrape_item.url)

        title = await self.create_title(scrape_item.url.name, None, None)
        albums = soup.select('a[class=album-link]')
        scrape_item.type = FILE_HOST_PROFILE

        try:
            scrape_item.children_limit = self.manager.config_manager.settings_data['Download_Options']['maximum_number_of_children'][scrape_item.type]
        except (IndexError, TypeError):
            pass

        for album in albums:
            link = URL(album['href'])
            new_scrape_item = await self.create_scrape_item(scrape_item, link, title, True, add_parent = scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.children += 1
            if scrape_item.children_limit:
                if scrape_item.children >= scrape_item.children_limit:
                    raise ScrapeItemMaxChildrenReached(scrape_item)

        next_page = soup.select_one('a[rel="next"]')
        if next_page:
            next_page = next_page.get("href").split("page=")[-1]
            new_scrape_item = await self.create_scrape_item(scrape_item,
                                                            scrape_item.url.with_query(f"page={next_page}"), "")
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0
        
        try:
            scrape_item.children_limit = self.manager.config_manager.settings_data['Download_Options']['maximum_number_of_children'][scrape_item.type]
        except (IndexError, TypeError):
            pass

        async with self.request_limiter:
            soup = await self.client.get_BS4(self.domain, scrape_item.url)

        title_portion = soup.select_one('title').text.rsplit(" - Porn")[0].strip()
        if not title_portion:
            title_portion = scrape_item.url.name
        title = await self.create_title(title_portion, scrape_item.url.parts[2], None)
        await scrape_item.add_to_parent_title(title)

        images = soup.select('img[class="img-front lasyload"]')
        videos = soup.select('div[class=media-group] div[class=video-lg] video source')

        image_links = [URL(image['data-src']) for image in images]
        video_links = [URL(video['src']) for video in videos]

        for link in image_links + video_links:
            filename, ext = await get_filename_and_ext(link.name)
            if not await self.check_album_results(link, results):
                await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.children += 1
            if scrape_item.children_limit:
                if scrape_item.children >= scrape_item.children_limit:
                    raise ScrapeItemMaxChildrenReached(scrape_item)