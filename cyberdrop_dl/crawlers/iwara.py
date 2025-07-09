from __future__ import annotations

import asyncio
import dataclasses
import datetime  # noqa: TC003
import hashlib
import itertools
from collections import defaultdict
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, TypeVar

from aiolimiter import AsyncLimiter
from pydantic import BaseModel, ConfigDict, Discriminator, Tag
from pydantic.alias_generators import to_camel

from cyberdrop_dl.compat import StrEnum
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DownloadError, ScrapeError
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncIterable

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://www.iwara.tv")
API_URL = AbsoluteHttpURL("https://api.iwara.tv")
IMAGE_CDN = AbsoluteHttpURL("https://i.iwara.tv/image/original/")
_X_VERSION_HEADER_SUFFIX = "5nFp9kmbNnHdAFhaqMvt"
_REQUEST_LIMIT = 50
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class IwaraModel(BaseModel):
    model_config: ConfigDict = ConfigDict(alias_generator=to_camel, defer_build=True)
    id: str


class FileType(StrEnum):
    image = "image"
    video = "video"


class File(IwaraModel):
    type: FileType
    name: str
    created_at: datetime.datetime


class User(IwaraModel):
    name: str
    username: str


class IwaraResponse(IwaraModel):
    title: str
    _type: FileType | Literal["playlist"]

    @property
    def web_url(self) -> AbsoluteHttpURL:
        return PRIMARY_URL / self._type / self.id


class Video(IwaraResponse):
    file: File
    file_url: str | None = None
    _type: Literal[FileType.video] = FileType.video


class Playlist(IwaraResponse):
    num_videos: int
    _type: Literal["playlist"] = "playlist"


class Image(IwaraResponse):
    files: list[File]
    _type: Literal[FileType.image] = FileType.image


def _results_discriminator(
    value: list[dict[str, Any]] | list[Video] | list[Image] | list[Playlist],
) -> str:
    if isinstance(value, list):
        if value:
            first = value[0]
            if isinstance(first, dict):
                if "files" in first:
                    return FileType.image
                if "numVideos" in first:
                    return "playlist"
            else:
                return first._type
    return FileType.video


class ResultsResponse(BaseModel):
    results: Annotated[
        Annotated[list[Video], Tag(FileType.video)]
        | Annotated[list[Image], Tag(FileType.image)]
        | Annotated[list[Playlist], Tag("playlist")],
        Discriminator(_results_discriminator),
    ]


class UserResponse(BaseModel):
    user: User


@dataclasses.dataclass(frozen=True, slots=True)
class Profile:
    username: str
    download_videos: bool
    download_images: bool
    download_playlists: bool

    @staticmethod
    def new(username: str, rest: list[str]) -> Profile:
        videos = images = playlists = False
        match rest:
            case ["videos"]:
                videos = True
            case ["images"]:
                images = True
            case ["playlists"]:
                playlists = True
            case []:
                videos = images = playlists = True
            case _:
                raise ValueError
        return Profile(username, videos, images, playlists)


class IwaraCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Profile": (
            "/profile/<username>",
            "/profile/<username>/videos",
            "/profile/<username>/images",
            "/profile/<username>/playlists",
        ),
        "Playlist": "/playlist/<playlist_id>",
        "Video": (
            "/video/<video_id>",
            "/video/<video_id>/<video_slug>",
        ),
        "Image": (
            "/image/<image_id>",
            "/image/<image_id>/<image_slug>",
        ),
        "Videos or images by tags": (
            "/videos?tags=...",
            "/images?tags=...",
        ),
        "Search": (
            "/search?type=images&query=...",
            "/search?type=video&query=...",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "iwara"

    def __post_init__(self) -> None:
        self._user_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._users: dict[str, User] = {}
        self.request_limiter = AsyncLimiter(4, 1)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["profile", user_name, *rest]:
                profile = Profile.new(user_name, rest)
                return await self.profile(scrape_item, profile)
            case ["playlist", playlist_id, *_]:
                return await self.playlist(scrape_item, playlist_id)
            case ["video", video_id, *_]:
                return await self.video(scrape_item, video_id)
            case ["image", image_id, *_]:
                return await self.image(scrape_item, image_id)
            case ["search"] if (search_type := scrape_item.url.query.get("type")) in FileType and (
                query := scrape_item.url.query.get("query")
            ):
                return await self.search(scrape_item, query, FileType(search_type))
            case ["videos" | "images" as tag_type] if tags := scrape_item.url.query.get("tags"):
                return await self.tags(scrape_item, tags, tag_type)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem, profile: Profile) -> None:
        user = await self._get_user(profile.username)
        scrape_item.setup_as_profile(self.create_title(user.name))

        async def iter_pages(name: str) -> None:
            url = PRIMARY_URL / profile.username / name
            if url.path_qs not in self.scraped_items:
                self.scraped_items.append(url.path_qs)
            new_scrape_item = scrape_item.create_child(url, new_title_part=name.capitalize())
            await self._iter_api_results(new_scrape_item, (API_URL / name).with_query(user=user.id))

        if profile.download_images:
            await iter_pages("images")
        if profile.download_videos:
            await iter_pages("videos")
        if profile.download_playlists:
            await iter_pages("playlists")

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, playlist_id: str) -> None:
        playlist = await self._make_api_request(Playlist, API_URL / "playlists" / playlist_id)
        await self._handle_playlist(scrape_item, playlist)

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem, image_id: str) -> None:
        image = await self._make_api_request(Image, API_URL / "image" / image_id)
        assert image.files
        await self._handle_image(scrape_item, image)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        scrape_item.url = PRIMARY_URL / "video" / video_id
        if await self.check_complete_from_referer(scrape_item):
            return
        video = await self._make_api_request(Video, API_URL / "video" / video_id)
        assert video.file_url
        await self._handle_video(scrape_item, video)

    @error_handling_wrapper
    async def tags(self, scrape_item: ScrapeItem, tags: str, tag_type: Literal["images", "videos"]) -> None:
        scrape_item.setup_as_profile(self.create_title(f"{tags} [tags]"))
        rating = scrape_item.url.query.get("rating", "all")
        await self._iter_api_results(scrape_item, (API_URL / tag_type).with_query(tags=tags, rating=rating))

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str, search_type: FileType) -> None:
        scrape_item.setup_as_profile(self.create_title(f"{query} [search]"))
        await self._iter_api_results(scrape_item, (API_URL / "search").with_query(query=query, type=search_type))

    async def _make_api_request(self, model_cls: type[_ModelT], api_url: AbsoluteHttpURL, /) -> _ModelT:
        try:
            async with self.request_limiter:
                response = await self.client._get_cffi(self.DOMAIN, api_url)
        except DownloadError as e:
            # TODO: Add login
            if e.status == 404 and not self.logged_in and (file_type := api_url.parts[1]) in FileType:
                raise ScrapeError(401, f"{file_type} has sensitive tags. Requires an account to view") from None
            raise
        return model_cls.model_validate_json(response.text, by_name=True, by_alias=True)

    @error_handling_wrapper
    async def _handle_playlist(self, scrape_item: ScrapeItem, playlist: Playlist) -> None:
        scrape_item.url = playlist.web_url
        title = self.create_title(f"{playlist.title} [playlist]", playlist.id)
        scrape_item.setup_as_profile(title, album_id=playlist.id)
        results = await self.get_album_results(playlist.id)
        await self._iter_api_results(scrape_item, API_URL / "playlist" / playlist.id, results)

    @error_handling_wrapper
    async def _handle_image(self, scrape_item: ScrapeItem, image: Image) -> None:
        scrape_item.url = image.web_url
        if not image.files:
            return await self.image(scrape_item, image.id)
        scrape_item.setup_as_album(self.create_title(image.title, image.id), album_id=image.id)
        results = await self.get_album_results(image.id)
        for file in image.files:
            url = IMAGE_CDN / file.id / file.name
            if self.check_album_results(url, results):
                continue
            new_scrape_item = scrape_item.copy()
            filename, ext = self.get_filename_and_ext(file.name)
            new_scrape_item.possible_datetime = to_timestamp(file.created_at)
            custom_filename = self.create_custom_filename(filename, ext, file_id=image.id)
            await self.handle_file(url, scrape_item, filename, ext, custom_filename=custom_filename)
            scrape_item.add_children()

    @error_handling_wrapper
    async def _handle_video(self, scrape_item: ScrapeItem, video: Video) -> None:
        scrape_item.url = video.web_url
        if not video.file_url:
            return await self.video(scrape_item, video.id)
        file_url = self.parse_url(video.file_url)
        headers = {"X-Version": _create_x_version_header(file_url)}
        async with self.request_limiter:
            sources: list[dict[str, Any]] = await self.client.get_json(self.DOMAIN, file_url, headers)

        original_src = next(src for src in sources if src["name"] == "Source")
        link = self.parse_url(original_src["src"]["download"])
        scrape_item.possible_datetime = to_timestamp(video.file.created_at)
        filename, ext = self.get_filename_and_ext(video.file.name)
        custom_filename = self.create_custom_filename(video.title, ext, file_id=video.id)
        await self.handle_file(
            scrape_item.url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
        )

    async def _get_user(self, username: str) -> User:
        async with self._user_locks[username]:
            if not self._users.get(username):
                user_resp = await self._make_api_request(UserResponse, API_URL / "profile" / username)
                self._users[username] = user_resp.user
            return self._users[username]

    async def _iter_api_results(
        self, scrape_item: ScrapeItem, url: AbsoluteHttpURL, playlist_results: dict[str, int] | None = None
    ) -> None:
        playlist_results = playlist_results or {}
        async for results in self._api_pager(url):
            for result in results:
                new_scrape_item = scrape_item.create_child(result.web_url)
                if result._type is FileType.video:
                    if self.check_album_results(result.web_url, playlist_results):
                        continue
                    coro = self._handle_video(new_scrape_item, result)
                elif result._type is FileType.image:
                    coro = self._handle_image(new_scrape_item, result)
                else:
                    coro = self._handle_playlist(new_scrape_item, result)
                self.manager.task_group.create_task(coro)
                scrape_item.add_children()

    async def _api_pager(self, url: AbsoluteHttpURL) -> AsyncIterable[list[Video] | list[Image] | list[Playlist]]:
        for page in itertools.count(0):
            api_url = url.update_query(page=page, limit=_REQUEST_LIMIT, sort="date")
            resp = await self._make_api_request(ResultsResponse, api_url)
            results = resp.results
            if not results:
                break
            yield results
            if len(results) < _REQUEST_LIMIT:
                break


def _create_x_version_header(file_url: AbsoluteHttpURL) -> str:
    expires = file_url.query["expires"]
    file_id = file_url.parts[2]
    x_version_header = f"{file_id}_{expires}_{_X_VERSION_HEADER_SUFFIX}"
    return hashlib.sha1(x_version_header.encode()).hexdigest()
