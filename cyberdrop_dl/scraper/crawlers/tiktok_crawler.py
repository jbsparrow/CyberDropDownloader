from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError, ScrapeError
from cyberdrop_dl.utils.utilities import log
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from typing import AsyncGenerator


class TikTokCrawler(Crawler):
    primary_base_domain = URL("https://tiktok.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "tiktok", "TikTok")
        self.api_url = URL("https://www.tikwm.com/api/")
        self.request_limiter = AsyncLimiter(1, 10)

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the URL."""
        # await self.test(scrape_item)
        
        if "@" in scrape_item.url.parts[1]:
            await self.profile(scrape_item)
        # else:
        #     await self.video(scrape_item)


    async def profile_post_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[dict]:
        """Generator for profile posts."""
        username = scrape_item.url.parts[1][1:]
        cursor = "0"
        while True:
            posts_api_url = (self.api_url / "user" / "posts").with_query({
                "cursor": cursor,
                "unique_id": username,
                "count": "50",
            })
            async with self.request_limiter:
                json_data = await self.client.get_json(self.primary_base_domain, posts_api_url, origin=scrape_item)
            has_next_page = json_data["data"]["hasMore"]
            if scrape_item.album_id is None:
                author_id = json_data["data"]["videos"][0]["author"]["id"]
                scrape_item.album_id = author_id
                new_title = self.create_title(username)
                scrape_item.add_to_parent_title(new_title)
            yield json_data
            if has_next_page:
                cursor = json_data["data"]["cursor"]
                continue
            break


    @error_handling_wrapper
    async def test(self, scrape_item: ScrapeItem) -> None:
        """Tests the TikTok crawler."""
        username = scrape_item.url.parts[1][1:]
        log(username)

    @error_handling_wrapper
    async def handle_image_post(self, scrape_item: ScrapeItem, post: dict) -> None:
        """Handles an image carousel post."""
        post_id = post["video_id"]
        title = post["title"] if post["title"] else f"Post {post_id}"
        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, title, True, post_id, post["create_time"])
        for image in post["images"]:
            image_url = URL(image)
            filename, ext = get_filename_and_ext(image_url.name)
            await self.handle_file(image_url, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a TikTok profile."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.part_of_album = True

        async for json_data in self.profile_post_pager(scrape_item):
            for item in json_data["data"]["videos"]:
                post_url = URL(item["play"])
                if len(item.get('images', [])) > 0:
                    await self.handle_image_post(scrape_item, item)
                    continue
                if str(post_url).endswith('mp3'):
                    continue
                filename, ext = f'{item["video_id"]}.mp4', "mp4"
                date = item['create_time']

                new_scrape_item = self.create_scrape_item(scrape_item, post_url, "", True, scrape_item.album_id, date)
                await self.handle_file(post_url, new_scrape_item, filename, ext)

    # @error_handling_wrapper
    # async def video(self, scrape_item: ScrapeItem) -> None:
    #     """Scrapes a TikTok video."""
    #     scrape_item.url = await self.get_stream_link(scrape_item.url)
    #     if await self.check_complete_from_referer(scrape_item):
    #         return

    #     async with self.request_limiter:
    #         video_url = scrape_item.url
    #         filename, ext = get_filename_and_ext(video_url.name)
    #         await self.handle_file(video_url, scrape_item, filename, ext)

