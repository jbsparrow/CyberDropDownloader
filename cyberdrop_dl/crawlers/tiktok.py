from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import call_w_valid_kwargs, error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

VIDEO_PARTS = "video", "photo", "v"
API_URL = AbsoluteHttpURL("https://www.tikwm.com/api/")
PRIMARY_URL = AbsoluteHttpURL("https://tiktok.com/")


@dataclasses.dataclass(frozen=True, slots=True)
class Author:
    id: str
    unique_id: str


@dataclasses.dataclass(frozen=True, slots=True)
# TODO: use pydantic for this
class Post:
    id: str
    title: str
    play: str
    music: str
    music_info: MusicInfo
    create_time: int
    author: Author
    images: list[str] = dataclasses.field(default_factory=list)

    @staticmethod
    def from_dict(video: dict[str, Any]):
        author = call_w_valid_kwargs(Author, video["author"])
        music_info = call_w_valid_kwargs(MusicInfo, video["music_info"])
        id_: str = video.get("id") or video["video_id"]
        kwargs = video | {"id": id_, "author": author, "music_info": music_info}
        return call_w_valid_kwargs(Post, kwargs)

    @property
    def canonical_url(self) -> AbsoluteHttpURL:
        return PRIMARY_URL / f"@{self.author.unique_id}/video/{self.id}"


@dataclasses.dataclass(frozen=True, slots=True)
class MusicInfo:
    title: str
    id: str
    play: str
    title: str
    original: bool

    @property
    def canonical_url(self) -> AbsoluteHttpURL:
        if self.original:
            name = "original-audio-{self.id}"
        else:
            name = f"{self.title.replace(' ', '-').lower()}-{self.id}"
        return PRIMARY_URL / "music" / name


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

    @property
    def separate_posts(self):
        return True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in VIDEO_PARTS) or scrape_item.url.host.startswith("vm.tiktok"):
            return await self.video(scrape_item)
        if "@" in (unique_id := scrape_item.url.parts[1]):
            return await self.profile(scrape_item, unique_id.removeprefix("@"))
        raise ValueError

    async def _profile_post_pager(self, unique_id: str) -> AsyncGenerator[Post]:
        cursor = 0
        while True:
            posts_api_url = (API_URL / "user" / "posts").with_query(
                cursor=cursor,
                unique_id=unique_id,
                count=50,
            )
            async with self.request_limiter:
                json_data: dict[str, Any] = await self.client.get_json(self.DOMAIN, posts_api_url)

            for post in json_data["data"]["videos"]:
                yield Post.from_dict(post)

            if not json_data["data"]["hasMore"]:
                break

            cursor = json_data["data"]["cursor"]

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem, unique_id: str) -> None:
        title: str = ""
        async for post in self._profile_post_pager(unique_id):
            if not title:
                title = self.create_title(unique_id, post.author.id)
                scrape_item.setup_as_profile(title)

            new_scrape_item = scrape_item.create_child(post.canonical_url)
            self.create_task(self._handle_post_task(new_scrape_item, post))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_data_url = API_URL.with_query(url=str(scrape_item.url))
        async with self.request_limiter:
            json_data = await self.client.get_json(self.DOMAIN, video_data_url)

        post = Post.from_dict(json_data["data"])
        scrape_item.url = post.canonical_url
        title = self.create_title(post.author.unique_id, post.id)
        scrape_item.setup_as_album(title, album_id=post.id)
        self._handle_post(scrape_item, post)

    def _handle_post(self, scrape_item: ScrapeItem, post: Post):
        post_title = self.create_separate_post_title(post.title, post.id, post.create_time)
        scrape_item.add_to_parent_title(post_title)
        scrape_item.possible_datetime = post.create_time
        self._handle_images(scrape_item, post)
        self._handle_audio(scrape_item, post)
        self._handle_video(scrape_item, post)

    _handle_post_task = auto_task_id(_handle_post)

    def _handle_video(self, scrape_item: ScrapeItem, post: Post):
        video_url = self.parse_url(post.play, trim=False)
        filename, ext = f"{post.id}.mp4", "mp4"
        self.create_task(self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=video_url))
        scrape_item.add_children()

    def _handle_images(self, scrape_item: ScrapeItem, post: Post) -> None:
        for url in post.images:
            link = self.parse_url(url, trim=False)
            filename, ext = self.get_filename_and_ext(link.name)
            self.create_task(self.handle_file(link, scrape_item, filename, ext))
            scrape_item.add_children()

    def _handle_audio(self, scrape_item: ScrapeItem, post: Post, new_folder: bool = True) -> None:
        if not self.manager.parsed_args.cli_only_args.download_tiktok_audios:
            return

        audio = post.music_info
        audio_url = self.parse_url(audio.play, trim=False)
        filename, ext = self.get_filename_and_ext(f"{audio.title}.mp3")
        self.create_task(self.handle_file(audio.canonical_url, scrape_item, filename, ext, debrid_link=audio_url))
        scrape_item.add_children()
