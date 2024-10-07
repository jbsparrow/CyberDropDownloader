from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem, FILE_HOST_ALBUM
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper, log
from cyberdrop_dl.clients.errors import ScrapeItemMaxChildrenReached

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class RealBooruCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "realbooru", "RealBooru")
        self.primary_base_url = URL("https://realbooru.com")
        self.request_limiter = AsyncLimiter(10, 1)

        self.cookies_set = False

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)

        await self.set_cookies()

        if "tags" in scrape_item.url.query_string:
            await self.tag(scrape_item)
        elif "id" in scrape_item.url.query_string:
            await self.file(scrape_item)
        else:
            await log(f"Scrape Failed: Unknown URL Path for {scrape_item.url}", 40)
            await self.manager.progress_manager.scrape_stats_progress.add_failure("Unsupported Link")

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        async with self.request_limiter:
            soup = await self.client.get_BS4(self.domain, scrape_item.url)

        title_portion = scrape_item.url.query['tags'].strip()
        title = await self.create_title(title_portion, None, None)
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0
        
        try:
            scrape_item.children_limit = self.manager.config_manager.settings_data['Download_Options']['maximum_number_of_children'][scrape_item.type]
        except (IndexError, TypeError):
            pass

        content = soup.select("div[class=items] div a")
        for file_page in content:
            link = file_page.get('href')
            if link.startswith("/"):
                link = f"{self.primary_base_url}{link}"
            link = URL(link, encoded=True)
            new_scrape_item = await self.create_scrape_item(scrape_item, link, title, True, add_parent = scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.children += 1
            if scrape_item.children_limit:
                if scrape_item.children >= scrape_item.children_limit:
                    raise ScrapeItemMaxChildrenReached(scrape_item)

        next_page = soup.select_one("a[alt=next]")
        if next_page is not None:
            next_page = next_page.get("href")
            if next_page is not None:
                if next_page.startswith("?"):
                    next_page = scrape_item.url.with_query(next_page[1:])
                else:
                    next_page = URL(next_page)
                new_scrape_item = await self.create_scrape_item(scrape_item, next_page, "")
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image"""
        async with self.request_limiter:
            soup = await self.client.get_BS4(self.domain, scrape_item.url)
        image = soup.select_one("img[id=image]")
        if image:
            link = URL(image.get('src'))
            filename, ext = await get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
        video = soup.select_one("video source")
        if video:
            link = URL(video.get('src'))
            filename, ext = await get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def set_cookies(self):
        """Sets the cookies for the client"""
        if self.cookies_set:
            return

        self.client.client_manager.cookies.update_cookies({"resize-original": "1"}, response_url=self.primary_base_url)

        self.cookies_set = True
