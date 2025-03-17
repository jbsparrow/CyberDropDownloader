from __future__ import annotations

import calendar
import datetime
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup, ResultSet, Tag

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


PRIMARY_BASE_DOMAIN = URL("https://spankbang.com/")
DEFAULT_QUALITY = "main"
RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst

VIDEO_REMOVED_SELECTOR = "[id='video_removed'], [class*='video_removed']"
PLAYLIST_ITEM_SELECTOR = "div.video-list > div.video-item > a"

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

    def get_page_url(self, page: int = 1) -> URL:
        return self.url / f"{page}"


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

        playlist = PlaylistInfo.from_url(scrape_item.url)
        scrape_item.url = playlist.url
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.album_id = playlist.id_
        results = await self.get_album_results(playlist.id_)

        async for title, page, videos in self.web_pager(scrape_item):
            if page == 1:
                title = self.create_title(title, playlist.id_)
                scrape_item.add_to_parent_title(title)

            for video in videos:
                link_str: str = video.get("href")  # type: ignore
                link = self.parse_url(link_str)
                if not self.check_album_results(link, results):
                    new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=playlist.url)
                    self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

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

        video_removed = soup.select_one(VIDEO_REMOVED_SELECTOR)
        if video_removed or "This video is no longer available" in str(soup):
            raise ScrapeError(410, origin=scrape_item)

        info = get_info_dict(soup)
        canonical_url = self.primary_base_domain / info["video_id"] / "video"
        if await self.check_complete_from_referer(canonical_url):
            return
        scrape_item.url = canonical_url

        v_format = get_best_quality(info)
        if not v_format:
            raise ScrapeError(422, origin=scrape_item)
        resolution, link_str = v_format
        date = parse_datetime(info["uploadDate"])
        link = self.parse_url(link_str)
        scrape_item.possible_datetime = date

        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = f"{info['title']} [{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[tuple[str, int, ResultSet[Tag]]]:
        """Generator of website pages."""
        page_url = scrape_item.url
        current_page = 1
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, page_url)

            playlist = PlaylistInfo.from_url(page_url, soup)
            videos = soup.select(PLAYLIST_ITEM_SELECTOR)
            yield playlist.title, current_page, videos
            if len(videos) < 100:
                break
            current_page += 1
            page_url = playlist.get_page_url(current_page)

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
    info: dict[str, str | dict] = javascript.parse_js_vars(info_js_script_text)
    extended_info_dict = javascript.parse_json_to_dict(extended_info_js_script_text)
    # type: ignore

    info["title"] = title.strip()
    info = info | extended_info_dict
    embed_url = URL(info["embedUrl"])
    info["video_id"] = embed_url.parts[1]
    javascript.clean_dict(info, "stream_data")
    log_debug(json.dumps(info, indent=4))
    return VideoInfo(**info)


def get_best_quality(info_dict: dict) -> Format:
    """Returns name and URL of the best available quality.

    Returns URL as `str`"""
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
