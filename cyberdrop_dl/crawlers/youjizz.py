from __future__ import annotations

import json
import re
from calendar import timegm
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, NamedTuple

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


DEFAULT_QUALITY = "Auto"
RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)


JS_SELECTOR = "div#content > script:contains('var dataEncodings')"
DATE_SELECTOR = "span.pretty-date"


class Format(NamedTuple):
    resolution: str
    link_str: str


## TODO: convert to global dataclass with constructor from dict to use in multiple crawlers
class VideoInfo(dict): ...


class YouJizzCrawler(Crawler):
    primary_base_domain = URL("https://www.youjizz.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "youjizz", "YouJizz")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
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
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        scrape_item.url = canonical_url
        info = get_info(soup)
        v_format = get_best_quality(info)
        if not v_format:
            raise ScrapeError(422)

        resolution, link_str = v_format

        link = self.parse_url(link_str)
        date_str: str | None = info["date"]
        if date_str:
            date = parse_relative_date(date_str)
            scrape_item.possible_datetime = date
        filename, ext = self.get_filename_and_ext(link.name)
        if ext == ".m3u8":
            raise ScrapeError(422)
        custom_filename = f"{info['title']} [{video_id}][{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_video_id(url: URL) -> str:
    if "embed" in url.parts:
        embed_index = url.parts.index("embed")
        return url.parts[embed_index + 1]

    video_id = url.parts[2].rsplit("-", 1)[-1]
    return video_id.removesuffix(".html")


def get_info(soup: BeautifulSoup) -> VideoInfo:
    info_js_script = soup.select_one(JS_SELECTOR)
    info_js_script_text: str = info_js_script.text  # type: ignore
    info: dict[str, str | None | dict] = javascript.parse_js_vars(info_js_script_text)  # type: ignore
    info["title"] = soup.title.text.replace("\n", "").strip()  # type: ignore
    date_tag = soup.select_one(DATE_SELECTOR)  # type: ignore
    date_str: str | None = date_tag.text if date_tag else None
    info["date"] = date_str.replace("(s)", "s").strip() if date_str else None
    javascript.clean_dict(info, "stream_data")
    log_debug(json.dumps(info, indent=4))
    return VideoInfo(**info)


def get_best_quality(info_dict: dict) -> Format | None:
    qualities: dict = info_dict["dataEncodings"]
    for res in RESOLUTIONS:
        avaliable_formats = [f for f in qualities if f["name"] == res]
        for format_info in avaliable_formats:
            link_str = format_info["filename"]
            if "/_hls/" not in link_str:
                return Format(res, link_str)
    default_quality: dict = next((f for f in qualities if f["name"] == DEFAULT_QUALITY), {})
    if default_quality:
        default_link_str = default_quality.get("filename") or ""
        return Format(DEFAULT_QUALITY, default_link_str)


## TODO: move to utils. multiple crawler use the same function
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
