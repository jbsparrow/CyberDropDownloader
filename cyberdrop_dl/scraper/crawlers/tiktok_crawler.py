from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

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
        if any(part in scrape_item.url.parts for part in ("video", "photo")):
            await self.video(scrape_item)
        elif len(scrape_item.url.parts)>0 and "@" in scrape_item.url.parts[1]::
            await self.profile(scrape_item)
        else:
            log(f"Scrape Failed: Unknown URL Path for {scrape_item.url}", 40)

    async def profile_post_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[dict]:
        username = scrape_item.url.parts[1][1:]
        cursor = "0"
        while True:
            posts_api_url = (self.api_url / "user" / "posts").with_query(
                {"cursor": cursor, "unique_id": username, "count": "50"}
            )
            async with self.request_limiter:
                json_data = await self.client.get_json(self.domain, posts_api_url, origin=scrape_item)

            if scrape_item.album_id is None:
                author_id = json_data["data"]["videos"][0]["author"]["id"]
                scrape_item.album_id = author_id
                scrape_item.add_to_parent_title(self.create_title(username, author_id))

            yield json_data

            if not json_data["data"]["hasMore"]:
                break
            cursor = json_data["data"]["cursor"]

    @error_handling_wrapper
    async def handle_image_post(self, scrape_item: ScrapeItem, post: dict) -> None:
        post_id = post["video_id"]
        title = post["title"] if post["title"] else f"Post {post_id}"
        new_scrape_item = self.create_scrape_item(
            scrape_item, scrape_item.url, title, True, post_id, post["create_time"]
        )
        for image_url in map(URL, post["images"]):
            filename, ext = get_filename_and_ext(image_url.name)
            scrape_item.add_children()
            await self.handle_file(image_url, new_scrape_item, filename, ext)
        if self.manager.parsed_args.cli_only_args.download_tiktok_audios:
            await self.handle_audio(new_scrape_item, post, False)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)
        async for json_data in self.profile_post_pager(scrape_item):
            for item in json_data["data"]["videos"]:
                post_url = URL(item["play"])
                if item.get("images"):
                    await self.handle_image_post(scrape_item, item)
                elif not post_url.path.endswith("mp3"):
                    filename, ext = f'{item["video_id"]}.mp4', "mp4"
                    new_scrape_item = self.create_scrape_item(
                        scrape_item, post_url, "", True, scrape_item.album_id, item["create_time"]
                    )
                    scrape_item.add_children()
                    if self.manager.parsed_args.cli_only_args.download_tiktok_audios:
                        await self.handle_audio(new_scrape_item, item)
                    await self.handle_file(post_url, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            video_data_url = self.api_url.with_query({"url": str(scrape_item.url)})
            json_data = await self.client.get_json(self.primary_base_domain, video_data_url, origin=scrape_item)

            if scrape_item.album_id is None:
                scrape_item.album_id = json_data["data"]["author"]["id"]
                scrape_item.add_to_parent_title(self.create_title(scrape_item.url.parts[1][1:]))

            json_data["data"]["video_id"] = json_data["data"].get("id")
            if json_data["data"].get("images"):
                await self.handle_image_post(scrape_item, json_data["data"])
                return

            video_url = URL(json_data["data"]["play"])
            filename, ext = f'{json_data["data"]["video_id"]}.mp4', "mp4"
            new_scrape_item = self.create_scrape_item(
                scrape_item, video_url, "", True, scrape_item.album_id, json_data["data"]["create_time"]
            )
            scrape_item.add_children()
            if self.manager.parsed_args.cli_only_args.download_tiktok_audios:
                await self.handle_audio(new_scrape_item, json_data["data"])
            await self.handle_file(video_url, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_audio(self, scrape_item: ScrapeItem, data: dict, new_folder: bool = True) -> None:
        audio_url = URL(data["music_info"]["play"])
        filename = f'{data["music_info"]["title"]}.mp3'
        new_scrape_item = self.create_scrape_item(
            scrape_item, audio_url, "Audios" if new_folder else "", True, scrape_item.album_id, data["create_time"]
        )
        scrape_item.add_children()
        await self.handle_file(audio_url, new_scrape_item, filename, "mp3")
