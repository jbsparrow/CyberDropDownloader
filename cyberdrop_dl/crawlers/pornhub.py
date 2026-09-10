from __future__ import annotations

import dataclasses
import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypedDict, final

from cyberdrop_dl.cache import cached_method
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, extr_text, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterable

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


@final
class Selector:
    FLASHVARS = "script:-soup-contains-own('var flashvars_')"
    GIF = "div#js-gifToWebm"
    NEXT_PAGE = "li.page_next a"
    PHOTO = "div#photoImageSection img"

    @final
    class Playlist:
        TITLE = "h1.playlistTitle"
        VIDEOS = "ul#videoPlaylist a.linkVideoThumb"

    @final
    class Album:
        FROM_PHOTO = "div#thumbSlider > h2 > a"
        TITLE = "h1[class*=photoAlbumTitle]"

    @final
    class Profile:
        NAME = ".topProfileHeader h1[itemprop=name], .profileUserName [title], div.title h1"
        VIDEOS = "div.container a.linkVideoThumb"
        GIFS = "#moreData li.gifLi a"
        ALBUMS = "#moreData.photosAlbumsListing a"


class PornHubCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/album/<album_id>",
        "Channel": "/channel/<name>",
        "Gif": "/gif/<gif_id>",
        "Photo": "/photo/<photo_id>",
        "Playlist": "/playlist/<playlist_id>",
        "Profile": (
            "/users/<name>",
            "/model/<name>",
            "/pornstar/<name>",
        ),
        "Profile videos": (
            "/users/<name>/videos",
            "/model/<name>/videos",
            "/pornstar/<name>/videos",
        ),
        "Profile uploaded videos": (
            "/users/<name>/videos/upload",
            "/model/<name>/videos/upload",
            "/pornstar/<name>/videos/upload",
        ),
        "Profile clips": (
            "/users/<name>/clips",
            "/model/<name>/clips",
            "/pornstar/<name>/clips",
        ),
        "Profile albums": (
            "/users/<name>/photos",
            "/model/<name>/photos",
            "/pornstar/<name>/photos",
        ),
        "Profile gifs": (
            "/users/<name>/gifs",
            "/model/<name>/gifs",
            "/pornstar/<name>/gifs",
        ),
        "Video": (
            "/embed/<video_id>",
            "/view_video.php?viewkey=<video_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.pornhub.com")
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE
    DOMAIN: ClassVar[str] = "pornhub"
    FOLDER_DOMAIN: ClassVar[str] = "PornHub"

    def __post_init__(self) -> None:
        self.api: PornHubAPI = PornHubAPI.from_crawler(self)
        self.update_cookies(
            dict.fromkeys(
                (
                    "age_verified",
                    "accessPH",
                    "accessAgeDisclaimerPH",
                    "accessAgeDisclaimerUK",
                    "expiredEnterModalShown",
                ),
                2,
            )
        )

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [
                "user" | "users" | "channel" | "channels" | "model" | "models" | "pornstar" | "pornstars" as type_,
                name,
                *_,
            ]:
                await PornHubProfileCrawler(self, Profile(type_, name), scrape_item).fetch()
            case ["album", album_id]:
                await self.album(scrape_item, album_id)
            case ["playlist", playlist_id]:
                await self.playlist(scrape_item, playlist_id)
            case ["photo", photo_id]:
                await self.photo(scrape_item, photo_id)
            case ["gif", gif_id]:
                await self.gif(scrape_item, gif_id)
            case ["embed", video_id]:
                await self.video(scrape_item, video_id)
            case ["view_video.php"] if video_id := scrape_item.url.query.get("viewkey"):
                await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        album = await self.api.album(album_id)
        scrape_item.setup_as_album(self.create_title(album.name, album.id), album_id=album.id)
        downloaded = await self.get_album_results(album.id)

        async for photo in self.api.album_photos(album.id):
            if self.check_album_results(photo.canonical_url, downloaded):
                continue
            web_url = self.PRIMARY_URL / "photo" / photo.id
            new_item = scrape_item.create_child(web_url)
            self.create_eager_task(self._photo(new_item, photo))
            scrape_item.add_children()

    @error_handling_wrapper
    async def photo(self, scrape_item: ScrapeItem, photo_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        src = css.select(soup, Selector.PHOTO, "src")
        album = _extr_album(soup)
        scrape_item.setup_as_album(self.create_title(album.name, album.id), album_id=album.id)
        await self._photo(scrape_item, Photo(photo_id, self.parse_url(src)))

    @error_handling_wrapper
    async def gif(self, scrape_item: ScrapeItem, gif_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        gif = css.select(soup, Selector.GIF)
        attrs = ("data-mp4", "data-fallback", "data-webm")
        src = next(value for attr in attrs if (value := css.attr_or_none(gif, attr)))
        scrape_item.uploaded_at = json_ld.upload_date(soup)
        await self._photo(scrape_item, Photo(gif_id, self.parse_url(src)))

    @error_handling_wrapper
    async def _photo(self, scrape_item: ScrapeItem, photo: Photo) -> None:
        filename, ext = self.get_filename_and_ext(photo.name, assume_ext=".jpg")
        await self.handle_file(
            photo.canonical_url,
            scrape_item,
            photo.original_name,
            ext,
            custom_filename=filename,
            debrid_link=photo.src,
        )

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, playlist_id: str) -> None:
        soup = await self.request_soup(scrape_item.url)
        title: str = css.select_text(soup, Selector.Playlist.TITLE)
        title = self.create_title(title, playlist_id)
        scrape_item.setup_as_album(f"{title} [playlist]", album_id=playlist_id)
        for new_scrape_item in self.iter_children(scrape_item, soup, Selector.Playlist.VIDEOS):
            self.create_task(self.run(new_scrape_item, check_referer=True))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        embed_url = self.PRIMARY_URL / "embed" / video_id

        if await self.check_complete(embed_url):
            return

        video = await self.api.video(video_id)
        scrape_item.uploaded_at = video.uploaded_at
        src = max(f for f in video.formats if f.format == "hls")
        m3u8, _ = await self.request_m3u8_playlist(self.parse_url(src.url), headers={"Referer": str(video.url)})

        scrape_item.url = video.url
        filename = self.create_custom_filename(video.title, ext := ".mp4", file_id=video_id, resolution=src.resolution)
        await self.handle_file(
            embed_url,
            scrape_item,
            video.title,
            ext,
            custom_filename=filename,
            m3u8=m3u8,
            thumbnail=video.thumb,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class PornHubProfileCrawler:
    crawler: PornHubCrawler
    profile: Profile
    item: ScrapeItem

    async def fetch(self) -> None:
        with self.crawler.catch_errors(self.item):
            match self.item.url.parts[3:]:
                case ["videos" | "clips", *_]:
                    await self.pages(Selector.Profile.VIDEOS)
                case ["gifs", *_]:
                    await self.pages(Selector.Profile.GIFS)
                case ["photos", *_]:
                    await self.pages(Selector.Profile.ALBUMS)
                case []:
                    await self.dispatch()
                case _:
                    raise ScrapeError.unsupported()

    async def dispatch(self) -> None:
        await self._init()
        for path in self.crawler.config.crawlers.pornhub.profile_paths:
            new_item = self.item.create_child(self.profile.url / path)
            self.crawler.create_task(self.crawler.run(new_item))
            self.item.add_children()

    async def pages(self, selector: str) -> None:
        await self._init()
        self.item.append_folders(*filter(None, self.item.url.parts[3:]))
        await self._iter_pages(selector)

    async def _init(self) -> None:
        if self.profile in self.item.markers:
            return

        soup = await self.crawler.request_soup(self.profile.url)
        name = css.select_text(soup, Selector.Profile.NAME, decompose="span")
        title = self.crawler.create_title(f"{name} [{self.profile.type.removesuffix('s')}]")
        self.item.setup_as_profile(title)
        self.item.markers.append(self.profile)

    async def _iter_pages(self, selector: str) -> None:
        async for soup in self.crawler.web_pager(self.item.url):
            for new_item in self.crawler.iter_children(self.item, soup, selector):
                self.crawler.create_task(self.crawler.run(new_item))


@dataclasses.dataclass(frozen=True, slots=True)
class Profile:
    type: str
    name: str

    @property
    def url(self) -> AbsoluteHttpURL:
        return PornHubCrawler.PRIMARY_URL / self.type / self.name


@dataclasses.dataclass(slots=True, order=True)
class Photo:
    id: str
    src: AbsoluteHttpURL

    name: str = dataclasses.field(init=False)
    original_name: str = dataclasses.field(init=False)
    canonical_url: AbsoluteHttpURL = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.original_name = self.src.name.rpartition(")")[-1]
        self.name = self.original_name.removeprefix("original_")
        self.canonical_url = self.src.with_name(self.name)


@dataclasses.dataclass(order=True, slots=True, frozen=True)
class Album:
    id: str
    name: str


class Media(TypedDict):
    height: int
    width: int
    format: Literal["hls", "mp4"]
    videoUrl: str
    quality: str | int | list[str]


@dataclasses.dataclass(slots=True, order=True, frozen=True)
class Format:
    resolution: Resolution
    format: Literal["hls", "mp4"]
    url: str


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class Video:
    id: str
    title: str
    thumb: str | None
    uploaded_at: float
    formats: tuple[Format, ...]
    url: AbsoluteHttpURL


class PornHubAPI(API):
    @cached_method(ttl=600)
    async def csrf_token(self) -> str:
        soup = await self.request_soup(self.PRIMARY_URL)
        return css.select(soup, "input[data-token]", "data-token")

    async def album(self, album_id: str) -> Album:
        url = self.PRIMARY_URL / "album" / album_id
        soup = await self.request_soup(url, impersonate="firefox")
        return Album(album_id, name=css.select_text(soup, Selector.Album.TITLE))

    async def album_photos(self, album_id: str) -> AsyncGenerator[Photo]:
        url = self.PRIMARY_URL / "api/v1/album" / album_id / "show_album_json"
        resp: dict[str, Any] = await self.request_json(url.with_query(token=await self.csrf_token()))
        photos: dict[str, dict[str, Any]] = resp["photos"]
        for photo_id, photo in photos.items():
            yield Photo(photo_id, self.parse_url(photo["img_large"]))

    async def video(self, video_id: str) -> Video:
        page_url = self.PRIMARY_URL.joinpath("view_video.php").with_query(viewkey=video_id)
        soup = await self.request_soup(page_url)
        _check_video_is_available(soup)
        flashvars = _extr_flashvars(soup)
        if flashvars.get("video_unavailable_country", "false") != "false":
            raise ScrapeError(HTTPStatus.FORBIDDEN, "Video is geo restricted")

        return Video(
            id=video_id,
            title=flashvars["video_title"],
            thumb=flashvars.get("image_url"),
            formats=tuple(_parse_formats(flashvars["mediaDefinitions"])),
            uploaded_at=json_ld.upload_date(soup),
            url=page_url,
        )


def _extr_album(soup: BeautifulSoup) -> Album:
    album = css.select(soup, Selector.Album.FROM_PHOTO)
    url: str = css.attr(album, "href")
    return Album(id=url.rpartition("/")[-1], name=css.text(album))


def _extr_flashvars(soup: BeautifulSoup) -> dict[str, Any]:
    flashvars: str = css.select_text(soup, Selector.FLASHVARS)
    payload = extr_text(flashvars, "{", "};").strip()
    return json.loads("{" + payload + "}")


def _parse_formats(medias: Iterable[Media]) -> Generator[Format]:
    for media in medias:
        quality = media["quality"]
        res = None
        if not isinstance(quality, list):
            try:
                quality = int(quality)
            except ValueError:
                pass

            try:
                res = Resolution.parse(quality)
            except ValueError:
                pass

        res = res or Resolution(media["height"], media["width"])

        yield Format(url=media["videoUrl"], format=media["format"], resolution=res)


def _check_video_is_available(soup: BeautifulSoup) -> None:
    if soup.select_one("section.noVideo"):
        raise ScrapeError(HTTPStatus.NOT_FOUND)

    page_text = soup.text
    if (
        soup.select_one(".geoBlocked > h1:-soup-contains('page is not available')")
        or "This content is unavailable in your country" in page_text
    ):
        raise ScrapeError(HTTPStatus.FORBIDDEN, "Video is geo restricted")

    if (
        "Video has been flagged for verification in accordance with our trust and safety policy" in page_text
        or "Video has been removed at the request of" in page_text
    ):
        raise ScrapeError(HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS)

    if (
        soup.select_one("div.removed")
        or "This video has been removed" in page_text
        or "This video is currently unavailable" in page_text
    ):
        raise ScrapeError(HTTPStatus.GONE)
