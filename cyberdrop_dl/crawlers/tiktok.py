from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, MediaItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, type_adapter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.utils import m3u8

VIDEO_PARTS = "video", "photo", "v"
API_URL = AbsoluteHttpURL("https://www.tikwm.com/api/")
PRIMARY_URL = AbsoluteHttpURL("https://tiktok.com/")


@dataclasses.dataclass(frozen=True, slots=True)
class Author:
    id: str
    unique_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class Post:
    id: str
    title: str
    play: str
    music_info: MusicInfo
    create_time: int
    author: Author
    images: list[str] = dataclasses.field(default_factory=list)

    @staticmethod
    def from_dict(video: dict[str, Any]) -> Post:
        video.update(
            id=video.get("id") or video["video_id"],
            author=_parse_author(video["author"]),
            music_info=_parse_music(video["music_info"]),
        )
        return _parse_post(video)

    @property
    def canonical_url(self) -> AbsoluteHttpURL:
        return PRIMARY_URL / f"@{self.author.unique_id}/video/{self.id}"


@dataclasses.dataclass(frozen=True, slots=True)
class MusicInfo:
    title: str
    id: str
    play: str
    original: bool

    @property
    def canonical_url(self) -> AbsoluteHttpURL:
        if self.original:
            name = f"original-audio-{self.id}"
        else:
            name = f"{self.title.replace(' ', '-').lower()}-{self.id}"
        return PRIMARY_URL / "music" / name


_parse_author = type_adapter(Author)
_parse_music = type_adapter(MusicInfo)
_parse_post = type_adapter(Post)


class TikTokCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "User": "/@<user>",
        "Video": "/@<user>/video/<video_id>",
        "Photo": "/@<user>/photo/<photo_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "tiktok"
    FOLDER_DOMAIN: ClassVar[str] = "TikTok"
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date:%Y-%m-%d} - {id}"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(1, 10)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in VIDEO_PARTS) or scrape_item.url.host.startswith("vm.tiktok"):
            return await self.video(scrape_item)
        if (unique_id := scrape_item.url.parts[1]).startswith("@"):
            return await self.profile(scrape_item, unique_id.removeprefix("@"))
        raise ValueError

    async def _api_request(self, url: AbsoluteHttpURL) -> dict[str, Any]:
        async with self.request_limiter:
            resp: dict[str, Any] = await self.client.get_json(self.DOMAIN, url)

        if (code := resp["code"]) != 0:
            raise ScrapeError(code, resp["msg"])

        return resp["data"]

    async def _profile_post_pager(self, unique_id: str) -> AsyncGenerator[list[Post]]:
        cursor: int = 0
        posts_api_url = (API_URL / "user" / "posts").with_query(unique_id=unique_id, count=50)
        while True:
            resp = await self._api_request(posts_api_url.update_query(cursor=cursor))

            yield [Post.from_dict(post) for post in resp["videos"]]

            if not resp["hasMore"]:
                break

            cursor = resp["cursor"]

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem, unique_id: str) -> None:
        title: str = ""
        async for posts in self._profile_post_pager(unique_id):
            for post in posts:
                if not title:
                    title = self.create_title(post.author.unique_id, post.author.id)
                    scrape_item.setup_as_profile(title)

                new_scrape_item = scrape_item.create_child(post.canonical_url)
                self._handle_post(new_scrape_item, post)
                scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_data_url = API_URL.with_query(url=str(scrape_item.url))
        json_data = await self._api_request(video_data_url)
        post = Post.from_dict(json_data)
        scrape_item.url = post.canonical_url
        title = self.create_title(post.author.unique_id, post.id)
        scrape_item.add_to_parent_title(title)
        self._handle_post(scrape_item, post)

    def _handle_post(self, scrape_item: ScrapeItem, post: Post) -> None:
        post_title = self.create_separate_post_title(post.title, post.id, post.create_time)
        scrape_item.setup_as_album(post_title, album_id=post.id)
        scrape_item.possible_datetime = post.create_time
        self._handle_images(scrape_item, post)
        self._handle_audio(scrape_item, post)
        self._handle_video(scrape_item, post)

    def _handle_video(self, scrape_item: ScrapeItem, post: Post) -> None:
        video_url = self.parse_url(post.play, trim=False)
        self.create_task(
            self.handle_file(
                scrape_item.url,
                scrape_item,
                filename=f"{post.id}.mp4",
                ext=".mp4",
                debrid_link=video_url,
            )
        )
        scrape_item.add_children()

    def _handle_images(self, scrape_item: ScrapeItem, post: Post) -> None:
        for url in post.images:
            link = self.parse_url(url, trim=False)
            filename, ext = self.get_filename_and_ext(link.name)
            self.create_task(self.handle_file(link, scrape_item, filename, ext))
            scrape_item.add_children()

    def _handle_audio(self, scrape_item: ScrapeItem, post: Post) -> None:
        if not self.manager.parsed_args.cli_only_args.download_tiktok_audios:
            return

        audio, ext = post.music_info, ".mp3"
        audio_url = self.parse_url(audio.play, trim=False)
        filename = self.create_custom_filename(audio.title, ext, file_id=audio.id)
        self.create_task(
            self.handle_file(
                audio.canonical_url,
                scrape_item,
                audio.title + ext,
                ext,
                debrid_link=audio_url,
                custom_filename=filename,
            )
        )
        scrape_item.add_children()

    async def handle_media_item(self, media_item: MediaItem, m3u8: m3u8.RenditionGroup | None = None) -> None:
        if media_item.ext == ".mp3":
            media_item.download_folder = media_item.download_folder / "Audios"

        await super().handle_media_item(media_item, m3u8)
