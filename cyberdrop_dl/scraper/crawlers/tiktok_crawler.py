from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext, log

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager


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

        if "video" in scrape_item.url.parts or "photo" in scrape_item.url.parts:
            await self.video(scrape_item)
        elif "@" in scrape_item.url.parts[1]:
            await self.profile(scrape_item)

    async def profile_post_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[dict]:
        """Generator for profile posts."""
        username = scrape_item.url.parts[1][1:]
        cursor = "0"
        while True:
            posts_api_url = (self.api_url / "user" / "posts").with_query(
                {
                    "cursor": cursor,
                    "unique_id": username,
                    "count": "50",
                }
            )
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
        new_scrape_item = self.create_scrape_item(
            scrape_item, scrape_item.url, title, True, post_id, post["create_time"]
        )
        for image in post["images"]:
            image_url = URL(image)
            filename, ext = get_filename_and_ext(image_url.name)
            scrape_item.add_children()
            await self.handle_file(image_url, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a TikTok profile."""
        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)

        async for json_data in self.profile_post_pager(scrape_item):
            for item in json_data["data"]["videos"]:
                post_url = URL(item["play"])
                if len(item.get("images", [])) > 0:
                    await self.handle_image_post(scrape_item, item)
                    continue
                if str(post_url).endswith("mp3"):
                    continue
                filename, ext = f'{item["video_id"]}.mp4', "mp4"
                date = item["create_time"]

                new_scrape_item = self.create_scrape_item(scrape_item, post_url, "", True, scrape_item.album_id, date)
                scrape_item.add_children()
                await self.handle_file(post_url, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a TikTok video."""

        async with self.request_limiter:
            video_data_url = self.api_url.with_query({"url": str(scrape_item.url)})
            json_data = await self.client.get_json(self.primary_base_domain, video_data_url, origin=scrape_item)

            username = scrape_item.url.parts[1][1:]
            if scrape_item.album_id is None:
                author_id = json_data["data"]["author"]["id"]
                scrape_item.album_id = author_id
                new_title = self.create_title(username)
                scrape_item.add_to_parent_title(new_title)

            json_data["data"]["video_id"] = json_data["data"]["id"]
            if len(json_data["data"].get("images", [])) > 0:
                await self.handle_image_post(scrape_item, json_data["data"])
                return

            video_url = URL(json_data["data"]["play"])
            filename, ext = f'{json_data["data"]["video_id"]}.mp4', "mp4"
            date = json_data["data"]["create_time"]

            new_scrape_item = self.create_scrape_item(scrape_item, video_url, "", True, scrape_item.album_id, date)
            scrape_item.add_children()
            await self.handle_file(video_url, new_scrape_item, filename, ext)
