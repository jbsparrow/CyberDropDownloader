from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, TypedDict

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import NoExtensionError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

PRIMARY_BASE_DOMAIN = URL("https://www.pornhub.com")
ALBUM_API_URL = PRIMARY_BASE_DOMAIN / "album/show_album_json"
PROFILE_PARTS = "user", "channel", "channels", "model", "pornstar"


@dataclass(order=True, slots=True, frozen=True)
class Profile:
    type: str
    name: str

    @property
    def url(self) -> URL:
        return PRIMARY_BASE_DOMAIN / self.type / self.name

    @property
    def has_photos(self) -> bool:
        return "channel" not in self.type


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

    PROFILE_GIFS = "li.gifLi a"
    PROFILE_TITLE = "div.title h1 , div.name h1[itemprop=name]"
    PROFILE_VIDEOS = "li[class*=VideoListItem] a.linkVideoThumb"
    PROFILE_ALBUMS = "div.photoAlbumListBlock > a"


_SELECTORS = Selectors()


class Media(TypedDict):
    height: int
    width: int
    format: Literal["hls", "mp4"]
    videoUrl: str
    quality: str | list

    # Not used
    defaultQuality: bool
    group: int
    remote: bool


class Format(NamedTuple):
    quality: int
    height: int
    width: int
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
    primary_base_domain = PRIMARY_BASE_DOMAIN
    next_page_selector = _SELECTORS.NEXT_PAGE

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pornhub", "PornHub")
        self._known_profiles_urls: set[URL] = set()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        # This logic prevents scraping 2 different URLs of the same profile, ex: /gifs and /videos
        # user can only scrape an entire profile or a single specific type per run
        if any(part in scrape_item.url.parts for part in PROFILE_PARTS):
            profile = Profile(*scrape_item.url.parts[1:3])
            if profile.url not in self._known_profiles_urls:
                self._known_profiles_urls.add(profile.url)
                return await self.profile(scrape_item, profile)

        if video_id := get_video_id(scrape_item.url):
            return await self.video(scrape_item, video_id)
        if "playlist" in scrape_item.url.parts:
            return await self.playlist(scrape_item)
        if "gif" in scrape_item.url.parts:
            return await self.gif(scrape_item)
        if "photo" in scrape_item.url.parts:
            return await self.photo(scrape_item)
        if "album" in scrape_item.url.parts:
            return await self.album(scrape_item)

        raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem, profile: Profile) -> None:
        title = await self._get_profile_title(scrape_item.url, profile)
        scrape_item.setup_as_profile(title)
        await self._proccess_profile_items(scrape_item, profile)

    async def _get_profile_title(self, url: URL, profile: Profile) -> str:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, url)
        title_tag = css.select_one(soup, _SELECTORS.PROFILE_TITLE)
        for span in css.iselect(title_tag, "span"):
            span.decompose()
        title = title_tag.get_text(strip=True)
        return self.create_title(f"{title} [{profile.type.removesuffix('s')}]")

    async def _proccess_profile_items(self, scrape_item: ScrapeItem, profile: Profile) -> None:
        scrape_all = scrape_item.url.path == profile.url.path
        scrape_videos = scrape_all or "videos" in scrape_item.url.parts
        scrape_gifs = profile.has_photos and (scrape_all or "gifs" in scrape_item.url.parts)
        scrape_photos = profile.has_photos and (scrape_all or "photos" in scrape_item.url.parts)
        init_page = int(scrape_item.url.query.get("page") or 1)

        def add_init_page(url: URL) -> URL:
            if scrape_item.url.path.startswith(url.path):
                return url.with_query(page=init_page)
            return url

        if scrape_videos:
            url = profile.url / "videos"
            await self._proccess_profile_pages(scrape_item, add_init_page(url), _SELECTORS.PROFILE_VIDEOS)

        if scrape_gifs:
            url = profile.url / "gifs/video"
            await self._proccess_profile_pages(scrape_item, add_init_page(url), _SELECTORS.PROFILE_GIFS)

        if scrape_photos:
            url = profile.url / "photos/public"
            await self._proccess_profile_pages(scrape_item, add_init_page(url), _SELECTORS.PROFILE_ALBUMS)

    @error_handling_wrapper
    async def _proccess_profile_pages(self, scrape_item: ScrapeItem, url: URL, selector: str) -> None:
        async for soup in self.web_pager(url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, selector):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        album_id = scrape_item.url.parts[2]
        api_url = ALBUM_API_URL.with_query(album=album_id)
        async with self.request_limiter:
            json_resp: dict[str, Any] = await self.client.get_json(self.domain, api_url)

        if not json_resp:
            return

        title = await self._get_album_title(scrape_item.url, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        results = await self.get_album_results(album_id)

        for id, photo in json_resp.items():
            web_url = self.primary_base_domain / "photo" / id
            link = self.parse_url(photo["img_large"])
            new_scrape_item = scrape_item.create_new(web_url)
            await self._proccess_photo(new_scrape_item, link, results)

    async def _get_album_title(self, url: URL, album_id: str) -> str:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, url)

        album_name: str = css.select_one(soup, _SELECTORS.ALBUM_TITLE).get_text(strip=True)
        return self.create_title(album_name, album_id)

    @error_handling_wrapper
    async def photo(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, scrape_item.url)

        link_str: str = css.select_one_get_attr(soup, _SELECTORS.PHOTO, "src")
        link = self.parse_url(link_str)
        album_tag = css.select_one(soup, _SELECTORS.ALBUM_FROM_PHOTO)
        album_name = album_tag.get_text(strip=True)
        album_link_str: str = css.get_attr(album_tag, "href")
        album_id: str = album_link_str.split("/")[-1]
        title = self.create_title(album_name, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        await self._proccess_photo(scrape_item, link)

    @error_handling_wrapper
    async def gif(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, scrape_item.url)

        attributes = "data-mp4", "data-fallback", "data-webm"
        gif_tag = css.select_one(soup, _SELECTORS.GIF)
        link_str = next(value for attr in attributes if (value := css.get_attr(gif_tag, attr)))
        link = self.parse_url(link_str)
        await self._proccess_photo(scrape_item, link)

    async def _proccess_photo(self, scrape_item: ScrapeItem, link: URL, results: dict[str, Any] | None = None) -> None:
        results = results or {}
        name = link.name.rsplit(")")[-1].removeprefix("original_")
        canonical_url = link.with_name(name)
        if not self.check_album_results(canonical_url, results):
            filename, ext = self.get_filename_and_ext(name, assume_ext=".jpg")
            await self.handle_file(canonical_url, scrape_item, filename, ext, debrid_link=link)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        playlist_id = scrape_item.url.parts[2]
        results = await self.get_album_results(playlist_id)
        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, scrape_item.url)

        title: str = css.select_one(soup, _SELECTORS.PLAYLIST_TITLE).get_text(strip=True)
        title = self.create_title(title, playlist_id)
        scrape_item.setup_as_album(f"{title} [playlist]", album_id=playlist_id)
        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.PLAYLIST_VIDEOS, results=results):
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        embed_url = self.primary_base_domain / "embed" / video_id
        page_url = self.primary_base_domain.joinpath("view_video.php").with_query(viewkey=video_id)

        if await self.check_complete_from_referer(page_url):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, page_url, cache_disabled=True)

        check_video_is_available(soup)
        title: str = css.select_one(soup, _SELECTORS.TITLE).get_text(strip=True)
        best_format = await self.get_best_format(soup)
        link = self.parse_url(best_format.url)
        scrape_item.url = page_url
        scrape_item.possible_datetime = self.parse_date(get_upload_date_str(soup))
        try:
            filename, ext = self.get_filename_and_ext(link.name)
        except NoExtensionError:
            filename, ext = self.get_filename_and_ext(f"{video_id}.mp4")
        custom_filename, _ = self.get_filename_and_ext(f"{title} [{video_id}][{best_format.quality}p].mp4")
        await self.handle_file(embed_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link)

    async def get_best_format(self, soup: BeautifulSoup) -> Format:
        mp4_format = next(get_mp4_formats(soup), None)
        if not mp4_format:
            raise ScrapeError(422)

        mp4_media_url = self.parse_url(mp4_format.url)
        async with self.request_limiter:
            mp4_media: list[Media] = await self.client.get_json(self.domain, mp4_media_url, cache_disabled=True)

        if not mp4_media:
            raise ScrapeError(422)

        return max(Format.new(media) for media in mp4_media)

    def set_cookies(self, _) -> None:
        keys = ("age_verified", "accessPH", "accessAgeDisclaimerPH", "accessAgeDisclaimerUK", "expiredEnterModalShown")
        cookies = dict.fromkeys(keys, 1)
        self.update_cookies(cookies)


def get_video_id(url: URL) -> str | None:
    if "embed" in url.parts and len(url.parts) > 2:
        return url.parts[2]
    if viewkey := url.query.get("viewkey"):
        return viewkey


def get_upload_date_str(soup: BeautifulSoup) -> str:
    date_text = css.select_one(soup, _SELECTORS.DATE).text
    return get_text_between(date_text, 'uploadDate": "', '",')


def get_mp4_formats(soup: BeautifulSoup) -> Generator[Format]:
    flashvars: str = css.select_one(soup, _SELECTORS.JS_VIDEO_INFO).text
    media_text = get_text_between(flashvars, 'mediaDefinitions":', ',"isVertical"')
    for media in json.loads(media_text):
        format = Format.new(media)
        if format.format == "mp4":
            yield format


def check_video_is_available(soup: BeautifulSoup) -> None:
    if soup.select_one(_SELECTORS.NO_VIDEO):
        raise ScrapeError(404)

    if soup.select_one(_SELECTORS.GEO_BLOCKED) or "This content is unavailable in your country" in soup.text:
        raise ScrapeError(403)

    if soup.select_one(_SELECTORS.REMOVED):
        raise ScrapeError(410)
