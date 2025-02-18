from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_PROFILE, ScrapeItem
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
        if any(part in scrape_item.url.parts for part in ("video", "photo", "v")) or scrape_item.url.host.startswith(
            "vm.tiktok"
        ):
            await self.video(scrape_item)
        elif len(scrape_item.url.parts) > 1 and "@" in scrape_item.url.parts[1]:
            await self.profile(scrape_item)
        else:
            raise ValueError

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
        author_id = post["author"]["id"]
        post_id = post["video_id"]
        canonical_url = await self.get_canonical_url(author_id, post_id)
        if await self.check_complete_from_referer(canonical_url):
            return

        title = post.get("title") or f"Post {post_id}"
        new_scrape_item = self.create_scrape_item(scrape_item, canonical_url, title, True, post_id, post["create_time"])
        for image_url in map(self.parse_url, post["images"]):
            filename, ext = get_filename_and_ext(image_url.name)
            await self.handle_file(image_url, new_scrape_item, filename, ext)
            scrape_item.add_children()
        await self.handle_audio(new_scrape_item, post, False)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)
        async for json_data in self.profile_post_pager(scrape_item):
            for item in json_data["data"]["videos"]:
                author_id = item["author"]["id"]
                post_id = item["video_id"]
                canonical_url = await self.get_canonical_url(author_id, post_id)
                if await self.check_complete_from_referer(canonical_url):
                    continue

                post_url = self.parse_url(item["play"])
                if item.get("images"):
                    await self.handle_image_post(scrape_item, item)
                elif not post_url.path.endswith("mp3"):
                    filename, ext = f"{item['video_id']}.mp4", "mp4"
                    new_scrape_item = self.create_scrape_item(
                        scrape_item, canonical_url, "", True, scrape_item.album_id, item["create_time"]
                    )
                    await self.handle_audio(new_scrape_item, item)
                    await self.handle_file(post_url, new_scrape_item, filename, ext)
                    scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            video_data_url = self.api_url.with_query({"url": str(scrape_item.url)})
            json_data = await self.client.get_json(self.domain, video_data_url, origin=scrape_item)

            author_id = json_data["data"]["author"]["id"]
            video_id = json_data["data"]["id"]
            canonical_url = await self.get_canonical_url(author_id, video_id)
            if await self.check_complete_from_referer(canonical_url):
                return

            if scrape_item.album_id is None:
                scrape_item.album_id = json_data["data"]["author"]["id"]
                scrape_item.add_to_parent_title(self.create_title(scrape_item.url.parts[1][1:]))

            json_data["data"]["video_id"] = json_data["data"].get("id")
            if json_data["data"].get("images"):
                await self.handle_image_post(scrape_item, json_data["data"])
                return

            video_url = self.parse_url(json_data["data"]["play"])
            filename, ext = f"{json_data['data']['video_id']}.mp4", "mp4"
            new_scrape_item = self.create_scrape_item(
                scrape_item, canonical_url, "", True, scrape_item.album_id, json_data["data"]["create_time"]
            )
            await self.handle_audio(new_scrape_item, json_data["data"])
            await self.handle_file(video_url, new_scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def handle_audio(self, scrape_item: ScrapeItem, data: dict, new_folder: bool = True) -> None:
        if not self.manager.parsed_args.cli_only_args.download_tiktok_audios:
            return
        title = data["music_info"]["title"]
        audio_id = data["music_info"]["id"]
        canonical_audio_url = await self.get_canonical_audio_url(title, audio_id)
        if await self.check_complete_from_referer(canonical_audio_url):
            return

        audio_url = self.parse_url(data["music_info"]["play"])
        filename = f"{data['music_info']['title']}.mp3"
        filename, ext = get_filename_and_ext(filename)
        new_scrape_item = self.create_scrape_item(
            scrape_item,
            canonical_audio_url,
            "Audios" if new_folder else "",
            True,
            scrape_item.album_id,
            data["create_time"],
        )

        await self.handle_file(audio_url, new_scrape_item, filename, ext)
        scrape_item.add_children()

    async def get_canonical_url(self, author: str, post_id: str | None = None) -> URL:
        if post_id is None:
            return self.primary_base_domain / f"@{author}"
        return self.primary_base_domain / f"@{author}/video/{post_id}"

    async def get_canonical_audio_url(self, audio_title: str, audio_id: str) -> URL:
        if "original audio" in audio_title.lower():
            return self.primary_base_domain / f"music/original-audio-{audio_id}"
        return self.primary_base_domain / f"music/{audio_title.replace(' ', '-').lower()}-{audio_id}"
