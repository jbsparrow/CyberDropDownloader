from __future__ import annotations

import dataclasses
import datetime
import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, ClassVar, Literal, NamedTuple, TypedDict

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://www.pornhub.com")
MP4_NOT_AVAILABLE_SINCE = datetime.datetime(2025, 6, 25).timestamp()
TOKEN_SELECTOR = css.CssAttributeSelector("input#xsrfToken", "value")


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

    GEO_BLOCKED = ".geoBlocked > h1:contains('page is not available')"
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
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        album_name = css.select_one_get_text(soup, _SELECTORS.ALBUM_TITLE)
        scrape_item.setup_as_album(self.create_title(album_name, album_id), album_id=album_id)

        api_url = self.PRIMARY_URL / "api/v1/album" / album_id / "show_album_json"
        async with self.request_limiter:
            json_resp: dict[str, Any] = await self.client.get_json(
                self.DOMAIN, api_url.with_query(token=TOKEN_SELECTOR(soup))
            )

        photos: dict[str, dict[str, Any]] = json_resp["photos"]
        results = await self.get_album_results(album_id)
        for id_, photo in photos.items():
            web_url = PRIMARY_URL / "photo" / id_
            link = self.parse_url(photo["img_large"])
            new_scrape_item = scrape_item.create_new(web_url)
            self.create_task(self._process_photo(new_scrape_item, link, results))
            scrape_item.add_children()

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
        original_name = link.name.rsplit(")")[-1]
        name = original_name.removeprefix("original_")
        canonical_url = link.with_name(name)
        if self.check_album_results(canonical_url, results):
            return
        custom_filename, ext = self.get_filename_and_ext(name, assume_ext=".jpg")
        await self.handle_file(
            canonical_url, scrape_item, original_name, ext, custom_filename=custom_filename, debrid_link=link
        )

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

        _check_video_is_available(soup)
        title = css.select_one_get_text(soup, _SELECTORS.TITLE)
        formats = [Format.new(media) for media in get_media_list(soup)]
        best_hls = max(f for f in formats if f.format == "hls")
        debrid_link = m3u8 = best_format = None
        scrape_item.possible_datetime = date = self.parse_iso_date(get_upload_date_str(soup))
        assert date
        use_hls = date >= MP4_NOT_AVAILABLE_SINCE

        if not use_hls:
            best_format = await self.get_best_mp4_format(formats)
            if best_format is None:
                self.log(
                    f"[{self.FOLDER_DOMAIN}] Video {video_id} has no mp4 formats available. Falling back to HLS", 30
                )

            else:
                debrid_link = self.parse_url(best_format.url)

        if use_hls or best_format is None:
            m3u8, _ = await self.get_m3u8_from_playlist_url(self.parse_url(best_hls.url))
            best_format = best_hls

        scrape_item.url = page_url
        filename, ext = self.get_filename_and_ext(f"{video_id}.mp4")
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id, resolution=best_format.quality)
        await self.handle_file(
            embed_url,
            scrape_item,
            filename,
            ext,
            custom_filename=custom_filename,
            debrid_link=debrid_link,
            m3u8=m3u8,
        )

    async def get_best_mp4_format(self, formats: list[Format]) -> Format | None:
        mp4_format = next((f for f in formats if f.format == "mp4"), None)
        if not mp4_format:
            raise ScrapeError(422, message="Unable to get mp4 format")

        mp4_media_url = self.parse_url(mp4_format.url)
        async with self.request_limiter:
            # This returns an empty list when downloading multiple videos concurrently
            mp4_media: list[Media] = await self.client.get_json(self.DOMAIN, mp4_media_url, cache_disabled=True)

        return max((Format.new(media) for media in mp4_media), default=None)


def get_upload_date_str(soup: BeautifulSoup) -> str:
    date_text = css.select_one_get_text(soup, _SELECTORS.DATE)
    return get_text_between(date_text, 'uploadDate": "', '",')


def get_media_list(soup: BeautifulSoup) -> list[Media]:
    flashvars: str = css.select_one(soup, _SELECTORS.JS_VIDEO_INFO).text
    media_text = get_text_between(flashvars, '"mediaDefinitions":', '"isVertical"').strip().removesuffix(",")
    return json.loads(media_text)


def _check_video_is_available(soup: BeautifulSoup) -> None:
    if soup.select_one(_SELECTORS.NO_VIDEO):
        raise ScrapeError(HTTPStatus.NOT_FOUND)

    page_text = soup.text
    if soup.select_one(_SELECTORS.GEO_BLOCKED) or "This content is unavailable in your country" in page_text:
        raise ScrapeError(HTTPStatus.FORBIDDEN, "Video is geo restricted")

    if (
        "Video has been flagged for verification in accordance with our trust and safety policy" in page_text
        or "Video has been removed at the request of" in page_text
    ):
        raise ScrapeError(HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS)

    if (
        soup.select_one(_SELECTORS.REMOVED)
        or "This video has been removed" in page_text
        or "This video is currently unavailable" in page_text
    ):
        raise ScrapeError(HTTPStatus.GONE)
