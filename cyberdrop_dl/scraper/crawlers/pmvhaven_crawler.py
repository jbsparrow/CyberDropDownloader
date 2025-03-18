from __future__ import annotations

import calendar
import json
from datetime import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


JS_VIDEO_INFO_SELECTOR = "script#__NUXT_DATA__"


class PMVHavenCrawler(Crawler):
    primary_base_domain = URL("https://pmvhaven.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pmvhaven", "PMVHaven")

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "video" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        video_info = get_video_info(soup)
        link_str: str = video_info.get("url") or ""
        if not link_str:
            raise ScrapeError(422, message="No video source found")

        video_id: str = video_info["_id"]
        resolution: str = video_info.get("height") or ""
        title: str = video_info.get("title") or video_info["uploadTitle"]
        link_str: str = video_info["url"]
        date = parse_datetime(video_info["isoDate"])

        scrape_item.possible_datetime = date
        link = self.parse_url(link_str)
        resolution = f"{resolution}p" if resolution else "Unknown"
        filename, ext = get_filename_and_ext(link.name)
        custom_filename, _ = get_filename_and_ext(f"{title} [{video_id}][{resolution}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_video_info(soup: BeautifulSoup) -> dict:
    info_js_script = soup.select_one(JS_VIDEO_INFO_SELECTOR)
    js_text = info_js_script.text if info_js_script else None
    if not js_text:
        raise ScrapeError(422)
    json_data: list = javascript.parse_json_to_dict(js_text, use_regex=False)  # type: ignore
    info_dict = {"data": json_data}
    javascript.clean_dict(info_dict)
    indices: dict[str, int] = {}
    video_properties = {}
    for elem in info_dict["data"]:
        if isinstance(elem, dict) and all(p in elem for p in ("uploadTitle", "isoDate")):
            indices = elem
            break
    for name, index in indices.items():
        video_properties[name] = info_dict["data"][index]

    log_debug(json.dumps(video_properties, indent=4))
    return video_properties


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.fromisoformat(date.replace("Z", "+00.00"))
    return calendar.timegm(parsed_date.timetuple())
