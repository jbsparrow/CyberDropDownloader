from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

VIDEO_PARTS = "video", "photo", "v"
API_URL = AbsoluteHttpURL("https://www.tikwm.com/api/")
PRIMARY_URL = AbsoluteHttpURL("https://tiktok.com/")


class TikTokCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "User": "/@<user>",
        "Video": "/@<user>/video/<video_id>",
        "Photo": "/@<user>/photo/<photo_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "tiktok"
    FOLDER_DOMAIN: ClassVar[str] = "TikTok"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(1, 10)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in VIDEO_PARTS) or scrape_item.url.host.startswith("vm.tiktok"):
            return await self.video(scrape_item)
        if len(scrape_item.url.parts) > 1 and "@" in scrape_item.url.parts[1]:
            return await self.profile(scrape_item)
        raise ValueError

    async def profile_post_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[dict[str, Any]]:
        username = scrape_item.url.parts[1].removeprefix("@")
        cursor = 0
        title: str = ""
        while True:
            posts_api_url = API_URL / "user" / "posts"
            posts_api_url = posts_api_url.with_query(cursor=cursor, unique_id=username, count=50)
            async with self.request_limiter:
                json_data = await self.client.get_json(self.DOMAIN, posts_api_url)

            if not title:
                author_id = json_data["data"]["videos"][0]["author"]["id"]
                title = self.create_title(username, author_id)
                scrape_item.setup_as_profile(title)

            yield json_data

            if not json_data["data"]["hasMore"]:
                break

            cursor = json_data["data"]["cursor"]

    @error_handling_wrapper
    async def handle_image_post(self, scrape_item: ScrapeItem, post: dict) -> None:
        author_id = post["author"]["id"]
        post_id = post["video_id"]
        canonical_url = _canonical_url(author_id, post_id)
        if await self.check_complete_from_referer(canonical_url):
            return

        title = post.get("title") or f"Post {post_id}"
        scrape_item.setup_as_album(title, album_id=post_id)
        scrape_item.possible_datetime = post["create_time"]
        scrape_item.url = canonical_url
        for url in post["images"]:
            link = self.parse_url(url, trim=False)
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()
        await self.handle_audio(scrape_item, post, False)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        async for json_data in self.profile_post_pager(scrape_item):
            for item in json_data["data"]["videos"]:
                author_id = item["author"]["id"]
                post_id = item["video_id"]
                canonical_url = _canonical_url(author_id, post_id)
                if await self.check_complete_from_referer(canonical_url):
                    continue

                post_url = self.parse_url(item["play"], trim=False)
                if item.get("images"):
                    await self.handle_image_post(scrape_item, item)
                    continue

                if post_url.path.endswith("mp3"):
                    continue

                filename, ext = f"{item['video_id']}.mp4", "mp4"
                new_scrape_item = scrape_item.create_child(canonical_url, possible_datetime=item["create_time"])
                await self.handle_audio(new_scrape_item, item)
                await self.handle_file(canonical_url, new_scrape_item, filename, ext, debrid_link=post_url)
                scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_data_url = API_URL.with_query(url=str(scrape_item.url))
        async with self.request_limiter:
            json_data = await self.client.get_json(self.DOMAIN, video_data_url)

        author_id = json_data["data"]["author"]["id"]
        video_id = json_data["data"]["video_id"] = json_data["data"]["id"]
        canonical_url = _canonical_url(author_id, video_id)
        if await self.check_complete_from_referer(canonical_url):
            return

        if scrape_item.album_id is None:
            album_id = json_data["data"]["author"]["id"]
            title = self.create_title(scrape_item.url.parts[1].removeprefix("@"), album_id)
            scrape_item.setup_as_album(title, album_id=album_id)

        if json_data["data"].get("images"):
            return await self.handle_image_post(scrape_item, json_data["data"])

        video_url = self.parse_url(json_data["data"]["play"], trim=False)
        filename, ext = f"{video_id}.mp4", "mp4"
        new_scrape_item = scrape_item.create_child(canonical_url, possible_datetime=json_data["data"]["create_time"])
        await self.handle_audio(new_scrape_item, json_data["data"])
        await self.handle_file(canonical_url, new_scrape_item, filename, ext, debrid_link=video_url)
        scrape_item.add_children()

    @error_handling_wrapper
    async def handle_audio(self, scrape_item: ScrapeItem, json_data: dict, new_folder: bool = True) -> None:
        if not self.manager.parsed_args.cli_only_args.download_tiktok_audios:
            return
        title = json_data["music_info"]["title"]
        audio_id = json_data["music_info"]["id"]
        canonical_audio_url = _canonical_audio_url(title, audio_id)
        if await self.check_complete_from_referer(canonical_audio_url):
            return

        audio_url = self.parse_url(json_data["music_info"]["play"], trim=False)
        filename = f"{json_data['music_info']['title']}.mp3"
        filename, ext = self.get_filename_and_ext(filename)
        new_scrape_item = scrape_item.create_child(
            canonical_audio_url,
            new_title_part="Audios" if new_folder else "",
            possible_datetime=json_data["create_time"],
        )

        await self.handle_file(canonical_audio_url, new_scrape_item, filename, ext, debrid_link=audio_url)
        scrape_item.add_children()


def _canonical_url(author: str, post_id: str | None = None) -> AbsoluteHttpURL:
    if post_id is None:
        return PRIMARY_URL / f"@{author}"
    return PRIMARY_URL / f"@{author}/video/{post_id}"


def _canonical_audio_url(audio_title: str, audio_id: str) -> AbsoluteHttpURL:
    if "original audio" in audio_title.lower():
        return PRIMARY_URL / f"music/original-audio-{audio_id}"
    return PRIMARY_URL / f"music/{audio_title.replace(' ', '-').lower()}-{audio_id}"
