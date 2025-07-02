from __future__ import annotations

import dataclasses
import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, ClassVar, Literal, NamedTuple, TypedDict

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import NoExtensionError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://www.pornhub.com")
ALBUM_API_URL = PRIMARY_URL / "album/show_album_json"


@dataclasses.dataclass(frozen=True, slots=True)
class Profile:
    type: str
    name: str
    download_videos: bool = dataclasses.field(compare=False)
    download_gifs: bool = dataclasses.field(compare=False)
    download_photos: bool = dataclasses.field(compare=False)

    @property
    def url(self) -> AbsoluteHttpURL:
        return PRIMARY_URL / self.type / self.name

    @staticmethod
    def new(type_: str, name: str, rest: list[str]) -> Profile:
        videos = gifs = photos = False
        match rest:
            case ["videos", *_]:
                videos = True
            case ["gifs", *_]:
                gifs = True
            case ["photos", *_]:
                photos = True
            case []:
                videos = True
                gifs = photos = "channel" not in type_
            case _:
                raise ValueError
        return Profile(type_, name, videos, gifs, photos)


class Selectors:
    ALBUM_FROM_PHOTO = "div#thumbSlider > h2 > a"
    ALBUM_TITLE = "h1[class*=photoAlbumTitle]"
    DATE = "script:contains('uploadDate')"
    GIF = "div#js-gifToWebm"
    JS_VIDEO_INFO = "script:contains('var flashvars_')"
    NEXT_PAGE = "li.page_next a"
    PHOTO = "div#photoImageSection img"
    PLAYLIST_TITLE = "h1.playlistTitle"
    PLAYLIST_VIDEOS = "ul#videoPlaylist a.linkVideoThumb"
    TITLE = "div.title-container > h1.title"

    GEO_BLOCKED = ".geoBlocked"
    NO_VIDEO = "section.noVideo"
    REMOVED = "div.removed"

    PROFILE_NAME = ".topProfileHeader h1[itemprop=name], div.title h1"
    PROFILE_VIDEOS = "div.container a.linkVideoThumb"
    PROFILE_GIFS = "#moreData li.gifLi a"
    PROFILE_ALBUMS = "#moreData.photosAlbumsListing a"


_SELECTORS = Selectors()


class Media(TypedDict):
    height: int
    width: int
    format: Literal["hls", "mp4"]
    videoUrl: str
    quality: str | list


class Format(NamedTuple):
    quality: int
    format: Literal["hls", "mp4"]
    url: str  # "videoUrl"

    @staticmethod
    def new(media: Media) -> Format:
        quality = media["quality"]
        if isinstance(quality, str):
            try:
                quality = int(quality)
            except ValueError:
                pass
        if not isinstance(quality, int):
            quality = min(media["height"], media["width"])
        values: dict[str, Any] = {k: v for k, v in media.items() if k in Format._fields} | {"quality": quality}
        return Format(url=media["videoUrl"], **values)


class PornHubCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/album/...",
        "Channel": "/channel/...",
        "Gif": "/gif/...",
        "Photo": "/photo/...",
        "Playlist": "/playlist/...",
        "Profile": (
            "/user/...",
            "/model/...",
            "/pornstar/...",
        ),
        "Video": (
            "/embed/<video_id>",
            "/view_video.php?viewkey=<video_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    DOMAIN: ClassVar[str] = "pornhub"
    FOLDER_DOMAIN: ClassVar[str] = "PornHub"

    def __post_init__(self) -> None:
        self.seen_profiles: set[Profile] = set()

    async def async_startup(self) -> None:
        keys = ("age_verified", "accessPH", "accessAgeDisclaimerPH", "accessAgeDisclaimerUK", "expiredEnterModalShown")
        self.update_cookies(dict.fromkeys(keys, 1))

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["user" | "channel" | "channels" | "model" | "pornstar" as type_, name, *rest]:
                profile = Profile.new(type_, name, rest)
                if profile in self.seen_profiles:
                    return
                self.seen_profiles.add(profile)
                return await self.profile(scrape_item, profile)
            case ["album", album_id]:
                return await self.album(scrape_item, album_id)
            case ["playlist", playlist_id]:
                return await self.playlist(scrape_item, playlist_id)
            case ["photo", _]:
                return await self.photo(scrape_item)
            case ["gif", _]:
                return await self.gif(scrape_item)
            case ["embed", video_id]:
                return await self.video(scrape_item, video_id)
            case ["view_video.php"] if video_id := scrape_item.url.query.get("viewkey"):
                return await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem, profile: Profile) -> None:
        title = await self._get_profile_title(profile.url)
        title = self.create_title(f"{title} [{profile.type.removesuffix('s')}]")
        scrape_item.setup_as_profile(title)

        if profile.download_videos:
            await self.iter_profile_pages(scrape_item, profile.url / "videos", _SELECTORS.PROFILE_VIDEOS)
        if profile.download_gifs:
            await self.iter_profile_pages(scrape_item, profile.url / "gifs/public", _SELECTORS.PROFILE_GIFS)
        if profile.download_photos:
            await self.iter_profile_pages(scrape_item, profile.url / "photos/public", _SELECTORS.PROFILE_ALBUMS)

    async def _get_profile_title(self, url: AbsoluteHttpURL) -> str:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, url)
        return css.select_one_get_text(soup, _SELECTORS.PROFILE_NAME, decompose="span")

    @error_handling_wrapper
    async def iter_profile_pages(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL, selector: str) -> None:
        async for soup in self.web_pager(url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, selector):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        api_url = ALBUM_API_URL.with_query(album=album_id)
        async with self.request_limiter:
            json_resp: dict[str, Any] = await self.client.get_json(self.DOMAIN, api_url)

        if not json_resp:
            return

        title = await self._get_album_title(scrape_item.url, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        results = await self.get_album_results(album_id)

        for id, photo in json_resp.items():
            web_url = PRIMARY_URL / "photo" / id
            link = self.parse_url(photo["img_large"])
            new_scrape_item = scrape_item.create_new(web_url)
            await self._process_photo(new_scrape_item, link, results)

    async def _get_album_title(self, url: AbsoluteHttpURL, album_id: str) -> str:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, url)

        album_name: str = css.select_one_get_text(soup, _SELECTORS.ALBUM_TITLE)
        return self.create_title(album_name, album_id)

    @error_handling_wrapper
    async def photo(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str: str = css.select_one_get_attr(soup, _SELECTORS.PHOTO, "src")
        link = self.parse_url(link_str)
        album_tag = css.select_one(soup, _SELECTORS.ALBUM_FROM_PHOTO)
        album_name = css.get_text(album_tag)
        album_link_str: str = css.get_attr(album_tag, "href")
        album_id: str = album_link_str.split("/")[-1]
        title = self.create_title(album_name, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        await self._process_photo(scrape_item, link)

    @error_handling_wrapper
    async def gif(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        attributes = "data-mp4", "data-fallback", "data-webm"
        gif_tag = css.select_one(soup, _SELECTORS.GIF)
        link_str = next(value for attr in attributes if (value := css.get_attr_or_none(gif_tag, attr)))
        link = self.parse_url(link_str)
        await self._process_photo(scrape_item, link)

    async def _process_photo(
        self, scrape_item: ScrapeItem, link: AbsoluteHttpURL, results: dict[str, Any] | None = None
    ) -> None:
        results = results or {}
        name = link.name.rsplit(")")[-1].removeprefix("original_")
        canonical_url = link.with_name(name)
        if self.check_album_results(canonical_url, results):
            return
        filename, ext = self.get_filename_and_ext(name, assume_ext=".jpg")
        await self.handle_file(canonical_url, scrape_item, filename, ext, debrid_link=link)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, playlist_id: str) -> None:
        results = await self.get_album_results(playlist_id)
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        title: str = css.select_one_get_text(soup, _SELECTORS.PLAYLIST_TITLE)
        title = self.create_title(title, playlist_id)
        scrape_item.setup_as_album(f"{title} [playlist]", album_id=playlist_id)
        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.PLAYLIST_VIDEOS, results=results):
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        embed_url = PRIMARY_URL / "embed" / video_id
        page_url = PRIMARY_URL.joinpath("view_video.php").with_query(viewkey=video_id)

        if await self.check_complete_from_referer(page_url):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, page_url, cache_disabled=True)

        check_video_is_available(soup)
        title: str = css.select_one_get_text(soup, _SELECTORS.TITLE)
        best_format = await self.get_best_format(soup)
        link = self.parse_url(best_format.url)
        scrape_item.url = page_url
        scrape_item.possible_datetime = self.parse_date(get_upload_date_str(soup))
        try:
            filename, ext = self.get_filename_and_ext(link.name)
        except NoExtensionError:
            filename, ext = self.get_filename_and_ext(f"{video_id}.mp4")
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id, resolution=best_format.quality)
        await self.handle_file(embed_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link)

    async def get_best_format(self, soup: BeautifulSoup) -> Format:
        mp4_format = next(get_mp4_formats(soup), None)
        if not mp4_format:
            raise ScrapeError(422)

        mp4_media_url = self.parse_url(mp4_format.url)
        async with self.request_limiter:
            mp4_media: list[Media] = await self.client.get_json(self.DOMAIN, mp4_media_url, cache_disabled=True)

        if not mp4_media:
            raise ScrapeError(422)

        return max(Format.new(media) for media in mp4_media)


def get_upload_date_str(soup: BeautifulSoup) -> str:
    date_text = css.select_one_get_text(soup, _SELECTORS.DATE)
    return get_text_between(date_text, 'uploadDate": "', '",')


def get_mp4_formats(soup: BeautifulSoup) -> Generator[Format]:
    for media in get_medias(soup):
        if media["format"] == "mp4":
            yield Format.new(media)


def get_medias(soup: BeautifulSoup) -> list[Media]:
    flashvars: str = css.select_one(soup, _SELECTORS.JS_VIDEO_INFO).text
    media_text = get_text_between(flashvars, 'mediaDefinitions":', ',"isVertical"')
    return json.loads(media_text)


def check_video_is_available(soup: BeautifulSoup) -> None:
    page_text = soup.text
    if soup.select_one(_SELECTORS.NO_VIDEO):
        raise ScrapeError(HTTPStatus.NOT_FOUND)

    if soup.select_one(_SELECTORS.GEO_BLOCKED) or "This content is unavailable in your country" in page_text:
        raise ScrapeError(HTTPStatus.FORBIDDEN)

    if any(
        text in page_text
        for text in (
            "Video has been flagged for verification in accordance with our trust and safety policy",
            "Video has been removed at the request of",
        )
    ):
        raise ScrapeError(HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS)

    if soup.select_one(_SELECTORS.REMOVED) or any(
        text in page_text for text in ("This video has been removed", "This video is currently unavailable")
    ):
        raise ScrapeError(HTTPStatus.GONE)
