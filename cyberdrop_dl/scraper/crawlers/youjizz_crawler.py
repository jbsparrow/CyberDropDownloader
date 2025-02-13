from __future__ import annotations

import json
import re
from calendar import timegm
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


DEFAULT_QUALITY = "Auto"
RESOLUTIONS = ["4k", "1080p", "720p", "480p", "320p", "240p"]  # best to worst
DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)


class YouJizzCrawler(Crawler):
    primary_base_domain = URL("https://www.youjizz.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "youjizz", "YouJizz")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        ## TODO: add tag support
        if any(p in scrape_item.url.parts for p in ("videos", "embed")):
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        video_id = get_video_id(scrape_item.url)
        canonical_url = self.primary_base_domain / "videos" / "embed" / video_id

        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.url = canonical_url
        info_dict = get_info_dict(soup)
        log_debug(json.dumps(info_dict, indent=4))
        resolution, link_str = get_best_quality(info_dict)
        if not link_str:
            raise ScrapeError(422, origin=scrape_item)

        link = self.parse_url(link_str)
        date = parse_relative_date(info_dict["date"])
        scrape_item.possible_datetime = date
        filename, ext = self.get_filename_and_ext(link.name)
        if ext == ".m3u8":
            raise ScrapeError(422, origin=scrape_item)
        custom_filename = f"{info_dict["title"]} [{video_id}][{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_video_id(url: URL) -> str:
    if "embed" in url.parts:
        embed_index = url.parts.index("embed")
        return url.parts[embed_index + 1]

    video_id = url.parts[2].rsplit("-", 1)[-1]
    return video_id.removesuffix(".html")


def get_info_dict(soup: BeautifulSoup) -> dict:
    info_js_script = soup.select_one("div#content > script:contains('var dataEncodings')")
    title = soup.title.text.replace("\n", "")  # type: ignore
    date_str = soup.select_one("span.pretty-date").text.replace("(s)", "s").strip()  # type: ignore
    info_dict: dict[str, str | dict] = {"title": title.strip(), "date": date_str}  # type: ignore
    return info_dict | parse_js_vars(info_js_script.text)  # type: ignore


def parse_js_vars(text: str) -> dict:
    info_dict = {}
    lines = [_.strip() for _ in text.split(";")]
    for line in lines:
        if not line.startswith("var "):
            continue
        data = line.removeprefix("var ")
        name, value = data.split("=", 1)
        name = name.strip()
        value = value.strip()
        info_dict[name] = value
        if value.startswith("{") or value.startswith("["):
            info_dict[name] = js_json_to_dict(value)
    clean_info_dict(info_dict)
    return info_dict


def js_json_to_dict(text: str) -> str:
    json_str = text.replace("'", '"')
    # wrap keys with double quotes
    json_str = re.sub(r"(\w+)\s?:", r'"\1":', json_str)
    # wrap values with double quotes, skip int or bool
    json_str = re.sub(r":\s?(?!(\d+|true|false))(\w+)", r':"\2"', json_str)
    return json.loads(json_str)


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
    qualities: dict = info_dict["dataEncodings"]
    for res in RESOLUTIONS:
        avaliable_formats = [f for f in qualities if f["name"] == res]
        for format_info in avaliable_formats:
            link_str = format_info["filename"]
            if "/_hls/" not in link_str:
                return res, link_str
    default_quality: dict = next((f for f in qualities if f["name"] == DEFAULT_QUALITY), {})
    default_link_str = default_quality.get("filename") or ""
    return DEFAULT_QUALITY, default_link_str


def parse_relative_date(relative_date: timedelta | str) -> int:
    """Parses `datetime.timedelta` or `string` in a timedelta format. Returns `now() - parsed_timedelta` as an unix timestamp."""
    if isinstance(relative_date, str):
        time_str = relative_date.casefold()
        matches: list[str] = re.findall(DATE_PATTERN, time_str)
        time_dict = {"days": 0}  # Assume today

        for value, unit in matches:
            value = int(value)
            unit = unit.lower()
            time_dict[unit] = value

        relative_date = timedelta(**time_dict)

    date = datetime.now() - relative_date
    return timegm(date.timetuple())
