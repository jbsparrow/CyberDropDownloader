from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, Self, override

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem
from cyberdrop_dl.utils.dataclass import DictDataclass
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from cyberdrop_dl.url_objects import ScrapeItem


_PRIMARY_URL = AbsoluteHttpURL("https://www.tiktok.com/")
_API_URL = AbsoluteHttpURL("https://www.tikwm.com/api/")
_API_SUBMIT_TASK_URL = _API_URL / "video/task/submit"
_API_TASK_RESULT_URL = _API_URL / "video/task/result"
_API_USER_POST_URL = _API_URL / "user/posts"


@dataclasses.dataclass(frozen=True, slots=True)
class Author(DictDataclass):
    id: str
    unique_id: str
    nickname: str

    def __str__(self) -> str:
        return f"@{self.unique_id}"


@dataclasses.dataclass(slots=True)
class Post(DictDataclass):
    id: str
    title: str
    play: str
    create_time: int
    size: int
    author: Author
    music_info: MusicInfo
    is_src_quality: bool = False
    images: list[str] = dataclasses.field(default_factory=list)
    canonical_url: AbsoluteHttpURL = dataclasses.field(default_factory=AbsoluteHttpURL)

    def __post_init__(self) -> None:
        part = "photo" if self.images else "video"
        self.canonical_url = _PRIMARY_URL / str(self.author) / part / self.id
        self.images = self.images or []

    @classmethod
    def from_dict(cls, video: Mapping[str, Any], /, **overrides: Any) -> Self:
        return super(Post, cls).from_dict(
            video,
            author=Author.from_dict(video["author"]),
            music_info=MusicInfo.from_dict(video["music_info"]),
            id=video.get("id") or video["video_id"],
            play=video.get("play") or video["play_url"],
            **overrides,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class MusicInfo(DictDataclass):
    title: str
    id: str
    play: str
    original: bool

    @property
    def canonical_url(self) -> AbsoluteHttpURL:
        safe_title = self.title.replace(" ", "-").lower()
        if "original-sound" in safe_title or "original-audio" in safe_title:
            safe_title = "original-audio"
        return _PRIMARY_URL / "music" / f"{safe_title}-{self.id}"


@HTTPConfig(rate_limit=(1, 2))
class TikTokCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "User": "/@<user>",
        "Video": (
            "/@<user>/video/<video_id>",
            "/@/video/<video_id>",
            "/share/video/<video_id>",
        ),
        "Photo": (
            "/@<user>/photo/<photo_id>",
            "/@/photo/<photo_id>",
            "/share/photo/<photo_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "tiktok"
    FOLDER_DOMAIN: ClassVar[str] = "TikTok"
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date:%Y-%m-%d} - {id}"

    @property
    def download_src_quality_videos(self) -> bool:
        return self.config.crawlers.tiktok.original

    def __post_init__(self) -> None:
        self._headers: dict[str, Any] = {"X-Requested-With": "XMLHttpRequest"}

    async def __async_post_init__(self) -> None:
        cookie_name = "sessionid"
        if value := self.cookies.get(cookie_name):
            self._headers["x-proxy-cookie"] = f"{cookie_name}={value}"
            self.log.info(f"Found {cookie_name} cookies")
        self.client.cookies.clear_domain(self.PRIMARY_URL.host)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_, "video" | "photo" | "v" as type_, media_id]:
                media_id = media_id.removesuffix(".html")
                if type_ != "photo" and self.download_src_quality_videos:
                    return await self.src_quality_media(scrape_item, media_id)
                return await self.media(scrape_item, media_id)
            case [profile] if profile.startswith("@"):
                return await self.profile(scrape_item, profile.removeprefix("@"))
            case _:
                raise ValueError

    async def _api_request(self, api_url: AbsoluteHttpURL) -> dict[str, Any]:
        resp: dict[str, Any] = await self.request_json(api_url, headers=self._headers)

        if (code := resp["code"]) != 0:
            msg = resp["msg"]
            if "Url parsing is failed" in msg:
                raise ScrapeError(410)
            raise ScrapeError(422, message=f"{code = }, {msg}")

        return resp["data"]

    async def _profile_post_pager(self, unique_id: str) -> AsyncGenerator[list[Post]]:
        cursor: int = 0
        api_url = _API_USER_POST_URL.with_query(unique_id=unique_id, count=50)
        while True:
            resp = await self._api_request(api_url.update_query(cursor=cursor))
            yield [Post.from_dict(post) for post in resp["videos"]]
            if not resp["hasMore"]:
                break

            cursor = resp["cursor"]

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem, unique_id: str) -> None:
        scrape_item.setup_as_profile("")
        async for posts in self._profile_post_pager(unique_id):
            for post in posts:
                new_scrape_item = scrape_item.create_child(post.canonical_url)
                if not post.images and self.download_src_quality_videos:
                    self.create_eager_task(self.src_quality_media_task(new_scrape_item, post.id, post))
                else:
                    self._handle_post(new_scrape_item, post)
                scrape_item.add_children()

    @error_handling_wrapper
    async def src_quality_media(self, scrape_item: ScrapeItem, media_id: str, post: Post | None = None) -> None:
        if await self.check_complete(scrape_item.url, scrape_item.url):
            return

        submit_url = _API_SUBMIT_TASK_URL.with_query(url=media_id)
        task_id: str = (await self._api_request(submit_url))["task_id"]
        self.log.info(f"trying to download {media_id = } with {task_id = }")
        json_data = await self._get_task_result(task_id)
        post = Post.from_dict(json_data["detail"])
        post.is_src_quality = True
        self._handle_post(scrape_item, post)

    src_quality_media_task = auto_task_id(src_quality_media)

    async def _get_task_result(self, task_id: str) -> dict[str, Any]:
        result_url = _API_TASK_RESULT_URL.with_query(task_id=task_id)
        delays = (0.5, 1.5, 4)
        for delay in delays:
            try:
                await asyncio.sleep(delay)
                return await self._api_request(result_url)
            except ScrapeError:
                pass

        msg = (
            f"[{self.FOLDER_DOMAIN}] Download {task_id = } was not ready "
            f"after {len(delays)} attempts. Total wait time: {sum(delays)}"
        )
        raise ScrapeError(503, msg)

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem, media_id: str) -> None:
        api_url = _API_URL.with_query(url=media_id)
        json_data = await self._api_request(api_url)
        post = Post.from_dict(json_data)
        self._handle_post(scrape_item, post)

    def _handle_post(self, scrape_item: ScrapeItem, post: Post) -> None:
        scrape_item.url = post.canonical_url
        title = self.create_title(post.author.unique_id, post.id)
        scrape_item.append_folders(title)
        post_title = self.create_separate_post_title(post.title, post.id, post.create_time)
        scrape_item.setup_as_album(post_title, album_id=post.id)
        scrape_item.uploaded_at = post.create_time
        self._handle_images(scrape_item, post)
        self._handle_audio(scrape_item, post)
        self._handle_video(scrape_item, post)

    def _handle_images(self, scrape_item: ScrapeItem, post: Post) -> None:
        for index, url in enumerate(post.images):
            link = self.parse_url(url, trim=False)
            img_url = post.canonical_url / str(index)
            filename = self.create_custom_filename(f"{post.id}_img{str(index).zfill(3)}", link.suffix)
            self.create_eager_task(
                self.handle_file(
                    img_url,
                    scrape_item,
                    filename,
                    link.suffix,
                    debrid_link=link,
                )
            )
            scrape_item.add_children()

    def _handle_audio(self, scrape_item: ScrapeItem, post: Post) -> None:
        audio, ext = post.music_info, ".mp3"
        audio_url = self.parse_url(audio.play, trim=False)
        filename = self.create_custom_filename(audio.title, ext, file_id=audio.id)
        self.create_eager_task(
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

    def _handle_video(self, scrape_item: ScrapeItem, post: Post) -> None:
        if not (post.size or post.play) or post.images:
            return

        video_url = self.parse_url(post.play, trim=False)
        ext = ".mp4"
        custom_filename = f"{post.id}{'_original'}{ext}" if post.is_src_quality else None
        self.create_eager_task(
            self.handle_file(
                scrape_item.url,
                scrape_item,
                post.id + ext,
                ext,
                debrid_link=video_url,
                custom_filename=custom_filename,
            )
        )
        scrape_item.add_children()

    @override
    def _prepare_media_item(self, media_item: MediaItem) -> None:
        if media_item.ext == ".mp3":
            media_item.download_folder /= "Audios"
