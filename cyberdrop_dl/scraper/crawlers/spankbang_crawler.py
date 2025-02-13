from __future__ import annotations

import calendar
import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


DEFAULT_QUALITY = "main"
RESOLUTIONS = ["4k", "1080p", "720p", "480p", "320p", "240p"]  # best to worst

VIDEO_REMOVED_SELECTOR = "[id='video_removed'], [class*='video_removed']"
PLAYLIST_ITEM_SELECTOR = "div.video-list > div.video-item > a"


class SpankBangCrawler(Crawler):
    primary_base_domain = URL("https://spankbang.com/")

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
        """Scrapes a playlist. Max 100 items per playlist"""
        playlist_id = scrape_item.url.parts[1]
        # TODO: add playlist pagination
        async with self.request_limiter:
            soup = get_test_soup()

        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.album_id = playlist_id
        title = soup.select_one("title").text.rsplit("Playlist -")[0].strip()  # type: ignore
        title = self.create_title(title, playlist_id)
        scrape_item.add_to_parent_title(title)

        results = await self.get_album_results(playlist_id)
        videos = soup.select(PLAYLIST_ITEM_SELECTOR)
        for video in videos:
            link_str: str = video.get("href")  # type: ignore
            link = self.parse_url(link_str)
            if not self.check_album_results(link, results):
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
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
            soup = get_test_soup()

        video_removed = soup.select_one(VIDEO_REMOVED_SELECTOR)
        if video_removed:
            raise ScrapeError(410, origin=scrape_item)

        info_dict = get_info_dict(soup)
        canonical_url = self.primary_base_domain / info_dict["video_id"] / "video"
        if await self.check_complete_from_referer(canonical_url):
            return
        scrape_item.url = canonical_url

        resolution, link_str = get_best_quality(info_dict)
        date = parse_datetime(info_dict["uploadDate"])
        link = self.parse_url(link_str)
        log_debug(json.dumps(info_dict, indent=4))
        scrape_item.possible_datetime = date

        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = f"{info_dict["title"]} [{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    def set_cookies(self) -> None:
        cookies = {"country": "US", "age_pass": 1}
        self.update_cookies(cookies)


def get_info_dict(soup: BeautifulSoup) -> dict:
    info_js_script = soup.select_one("main.main-container > script:contains('var stream_data')")
    extended_info_js_script = soup.select_one("main.main-container > script:contains('uploadDate')")
    title = soup.select_one("div#video h1")
    title = title.get("title") or title.text.replace("\n", "")  # type: ignore
    info_dict: dict[str, str | dict] = {"title": title.strip()}  # type: ignore
    lines = [_.strip() for _ in info_js_script.text.split(";")]  # type: ignore
    for line in lines:
        if not line.startswith("var "):
            continue
        data = line.removeprefix("var ")
        name, value = data.split("=", 1)
        name = name.strip()
        value = value.strip()
        info_dict[name] = value
        if value.startswith("{"):
            info_dict[name] = json.loads(value.replace("'", '"'))
    extended_info_dict = json.loads(extended_info_js_script.text.replace("'", '"'))  # type: ignore
    info_dict = info_dict | extended_info_dict
    embed_url = URL(info_dict["embedUrl"])  # type: ignore
    info_dict["video_id"] = embed_url.parts[1]
    clean_info_dict(info_dict)
    return info_dict


def clean_info_dict(info_dict: dict) -> None:
    """Modifies dict in place"""

    def is_valid_key(key: str) -> bool:
        return not any(p in key for p in ("@", "m3u8"))

    if "stream_data" in info_dict:
        info_dict["stream_data"] = {k: v for k, v in info_dict["stream_data"].items() if is_valid_key(k)}

    for k, v in info_dict.items():
        if isinstance(v, dict):
            continue
        info_dict[k] = clean_value(v)


def clean_value(value: list | str | int) -> list | str | int | None:
    if isinstance(value, str):
        value = value.removesuffix("'").removeprefix("'")
        if value.isdigit():
            return int(value)
        return value

    if isinstance(value, list):
        return [clean_value(v) for v in value]
    return value


def get_best_quality(info_dict: dict) -> tuple[str, str]:
    """Returns name and URL of the best available quality.

    Returns URL as `str`"""
    qualities: dict = info_dict["stream_data"]
    for res in RESOLUTIONS:
        value = qualities.get(res)
        if value:
            return res, value[-1]
    return DEFAULT_QUALITY, qualities[DEFAULT_QUALITY]


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S")
    return calendar.timegm(parsed_date.timetuple())


def get_test_soup() -> BeautifulSoup:
    file_html = Path("spankbang_playlist.htm").read_bytes()
    return BeautifulSoup(file_html, "html.parser")


def is_playlist(url: URL) -> bool:
    return "playlist" in url.parts and "-" not in url.parts[1]
