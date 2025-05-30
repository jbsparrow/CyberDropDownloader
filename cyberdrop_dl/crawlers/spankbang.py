from __future__ import annotations

import calendar
import datetime
import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.data_structures.url_objects import ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


PRIMARY_BASE_DOMAIN = URL("https://spankbang.com/")
DEFAULT_QUALITY = "main"
RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst

VIDEO_REMOVED_SELECTOR = "[id='video_removed'], [class*='video_removed']"
VIDEOS_SELECTOR = "div.video-list > div.video-item > a"

JS_SELECTOR = "main.main-container > script:contains('var stream_data')"
EXTENDED_JS_SELECTOR = "main.main-container > script:contains('uploadDate')"


@dataclass(frozen=True)
class PlaylistInfo:
    id_: str
    url: URL
    title: str = ""

    @classmethod
    def from_url(cls, url: URL, soup: BeautifulSoup | None = None) -> PlaylistInfo:
        playlist_id = url.parts[1].split("-")[0]
        name = url.parts[3]
        canonical_url = PRIMARY_BASE_DOMAIN / playlist_id / "playlist" / name
        title = soup.select_one("title").text.rsplit("Playlist -")[0].strip() if soup else ""  # type: ignore
        return cls(playlist_id, canonical_url, title)


class Format(NamedTuple):
    resolution: str
    link_str: str


## TODO: convert to global dataclass with constructor from dict to use in multiple crawlers
class VideoInfo(dict): ...


class SpankBangCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "spankbang", "SpankBang")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        self.set_cookies()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if is_playlist(scrape_item.url):
            return await self.playlist(scrape_item)
        if any(p in scrape_item.url.parts for p in ("video", "play", "embed", "playlist")):
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a playlist."""

        # Get basic playlist info from the URL
        playlist = PlaylistInfo.from_url(scrape_item.url)
        scrape_item.url = playlist.url
        results = await self.get_album_results(playlist.id_)
        page_url = scrape_item.url
        title: str = ""

        for page in itertools.count(1):
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, page_url)

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
        """Scrapes a video."""

        if "playlist" not in scrape_item.url.parts:
            video_id = scrape_item.url.parts[1]
            canonical_url = self.primary_base_domain / video_id / "video"
            if await self.check_complete_from_referer(canonical_url):
                return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)

        was_removed = soup.select_one(VIDEO_REMOVED_SELECTOR)
        if was_removed or "This video is no longer available" in str(soup):
            raise ScrapeError(410)

        info = get_info_dict(soup)
        canonical_url = self.primary_base_domain / info["video_id"] / "video"
        if await self.check_complete_from_referer(canonical_url):
            return
        scrape_item.url = canonical_url

        video_format = get_best_quality(info)
        if not video_format:
            raise ScrapeError(422)
        resolution, link_str = video_format
        scrape_item.possible_datetime = parse_datetime(info["uploadDate"])

        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename, _ = self.get_filename_and_ext(f"{info['title']} [{resolution}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    def set_cookies(self) -> None:
        cookies = {"country": "US", "age_pass": 1}
        self.update_cookies(cookies)


def get_info_dict(soup: BeautifulSoup) -> VideoInfo:
    info_js_script = soup.select_one(JS_SELECTOR)
    extended_info_js_script = soup.select_one(EXTENDED_JS_SELECTOR)

    info_js_script_text: str = info_js_script.text  # type: ignore
    extended_info_js_script_text: str = extended_info_js_script.text  # type: ignore

    title_tag = soup.select_one("div#video h1")
    title: str = title_tag.get("title") or title_tag.text.replace("\n", "")  # type: ignore
    del soup
    info: dict[str, Any] = javascript.parse_js_vars(info_js_script_text)
    extended_info_dict: dict = javascript.parse_json_to_dict(extended_info_js_script_text)  # type: ignore

    info["title"] = title.strip()
    info = info | extended_info_dict
    embed_url = URL(info["embedUrl"])
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


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S")
    return calendar.timegm(parsed_date.timetuple())


def is_playlist(url: URL) -> bool:
    return "playlist" in url.parts and "-" not in url.parts[1]
