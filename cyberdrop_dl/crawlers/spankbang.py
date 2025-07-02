from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://spankbang.com/")
DEFAULT_QUALITY = "main"
RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst

VIDEO_REMOVED_SELECTOR = "[id='video_removed'], [class*='video_removed']"
VIDEOS_SELECTOR = "div.video-list > div.video-item > a"

JS_SELECTOR = "main.main-container > script:contains('var stream_data')"
EXTENDED_JS_SELECTOR = "main.main-container > script:contains('uploadDate')"


@dataclass(frozen=True)
class PlaylistInfo:
    id_: str
    url: AbsoluteHttpURL
    title: str = ""

    @classmethod
    def from_url(cls, url: AbsoluteHttpURL, soup: BeautifulSoup | None = None) -> PlaylistInfo:
        playlist_id = url.parts[1].split("-")[0]
        name = url.parts[3]
        canonical_url = PRIMARY_URL / playlist_id / "playlist" / name
        title = css.select_one_get_text(soup, "title").rsplit("Playlist -")[0].strip() if soup else ""
        return cls(playlist_id, canonical_url, title)


class Format(NamedTuple):
    resolution: str
    link_str: str


## TODO: convert to global dataclass with constructor from dict to use in multiple crawlers
class VideoInfo(dict): ...


class SpankBangCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Playlist": "/playlist/<playlist-id>",
        "Video": (
            "/video/<video_id>",
            "/embed/<video_id>",
            "/play/<video_id>",
            "/playlist/<playlist-id>-<video_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "spankbang"
    FOLDER_DOMAIN: ClassVar[str] = "SpankBang"

    async def async_startup(self) -> None:
        self.set_cookies()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if is_playlist(scrape_item.url):
            return await self.playlist(scrape_item)
        if any(p in scrape_item.url.parts for p in ("video", "play", "embed", "playlist")):
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        # Get basic playlist info from the URL
        playlist = PlaylistInfo.from_url(scrape_item.url)
        scrape_item.url = playlist.url
        results = await self.get_album_results(playlist.id_)
        page_url = scrape_item.url
        title: str = ""

        for page in itertools.count(1):
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup_cffi(self.DOMAIN, page_url)

            # Get full playlist info + title from the soup
            playlist = PlaylistInfo.from_url(page_url, soup)
            if not title:
                title = self.create_title(playlist.title, playlist.id_)
                scrape_item.setup_as_album(title, album_id=playlist.id_)

            n_videos = 0

            for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEOS_SELECTOR, results=results):
                n_videos += 1
                self.manager.task_group.create_task(self.run(new_scrape_item))

            if n_videos < 100:
                break

            page_url = playlist.url / f"{page + 1}"

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if "playlist" not in scrape_item.url.parts:
            video_id = scrape_item.url.parts[1]
            canonical_url = PRIMARY_URL / video_id / "video"
            if await self.check_complete_from_referer(canonical_url):
                return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.DOMAIN, scrape_item.url)

        was_removed = soup.select_one(VIDEO_REMOVED_SELECTOR)
        if was_removed or "This video is no longer available" in str(soup):
            raise ScrapeError(410)

        info = get_info_dict(soup)
        canonical_url = PRIMARY_URL / info["video_id"] / "video"
        if await self.check_complete_from_referer(canonical_url):
            return
        scrape_item.url = canonical_url

        video_format = get_best_quality(info)
        if not video_format:
            raise ScrapeError(422)
        resolution, link_str = video_format
        scrape_item.possible_datetime = self.parse_iso_date(info["uploadDate"])
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(info["title"], ext, file_id=video_id, resolution=resolution)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    def set_cookies(self) -> None:
        cookies = {"country": "US", "age_pass": 1}
        self.update_cookies(cookies)


def get_info_dict(soup: BeautifulSoup) -> VideoInfo:
    info_js_script_text = css.select_one_get_text(soup, JS_SELECTOR)
    extended_info_js_script_text = css.select_one_get_text(soup, EXTENDED_JS_SELECTOR)

    title_tag = css.select_one(soup, "div#video h1")
    title: str = css.get_attr_or_none(title_tag, "title") or css.get_text(title_tag).replace("\n", "")
    del soup
    info: dict[str, Any] = javascript.parse_js_vars(info_js_script_text)
    extended_info_dict: dict = javascript.parse_json_to_dict(extended_info_js_script_text)

    info["title"] = title.strip()
    info = info | extended_info_dict
    embed_url = AbsoluteHttpURL(info["embedUrl"])
    info["video_id"] = embed_url.parts[1]
    javascript.clean_dict(info, "stream_data")
    log_debug(info)
    return VideoInfo(**info)


def get_best_quality(info_dict: dict) -> Format:
    """Returns name and URL of the best available quality."""
    qualities: dict = info_dict["stream_data"]
    for res in RESOLUTIONS:
        value = qualities.get(res)
        if value:
            return Format(res, value[-1])
    return Format(DEFAULT_QUALITY, qualities[DEFAULT_QUALITY])


def is_playlist(url: AbsoluteHttpURL) -> bool:
    return "playlist" in url.parts and "-" not in url.parts[1]
