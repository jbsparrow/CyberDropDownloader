from __future__ import annotations

import calendar
import json
from datetime import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


RESOLUTIONS = ["4k", "1080p", "720p", "480p", "320p", "240p"]  # best to worst
DOWNLOADS_SELECTOR = "div#tab_video_info div.row_spacer div.wrap > a.tag_item"
HTTPS_PLACEHOLDER = "<<SAFE_HTTPS>>"
HTTP_PLACEHOLDER = "<<SAFE_HTTP>>"


class Rule34VideoCrawler(Crawler):
    primary_base_domain = URL("https://rule34video.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34video", "Rule34Video")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        # TODO: add "categories", "models", "members" and "tags"
        if any(p in scrape_item.url.parts for p in ("video", "videos")):
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        video_id = scrape_item.url.parts[2]
        canonical_url = self.primary_base_domain / "video" / video_id

        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
            # soup = get_test_soup()

        scrape_item.url = canonical_url
        info_dict = get_info_dict(soup)
        _, link_str = get_best_quality(soup)
        log_debug(json.dumps(info_dict, indent=4))

        link = self.parse_url(link_str)
        log_debug(str(link))

        scrape_item.possible_datetime = parse_datetime(info_dict["uploadDate"])
        name = link.name or link.parent.name
        filename, ext = self.get_filename_and_ext(name)
        custom_filename = link.query.get("download_filename") or info_dict["title"]
        custom_filename = f"{custom_filename} [{video_id}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_info_dict(soup: BeautifulSoup) -> dict:
    title = soup.select_one("h1.title_video").text.strip()  # type: ignore
    info_js_script = soup.select_one("head > script:contains('uploadDate')")
    info_dict: dict[str, str | dict] = {"title": title.strip()}  # type: ignore
    info_dict = info_dict | javascript.parse_json_to_dict(info_js_script.text)  # type: ignore
    javascript.clean_dict(info_dict)
    return info_dict


def get_best_quality(soup: BeautifulSoup) -> tuple[str, str]:
    """Returns name and URL of the best available quality.

    Returns URL as `str`"""

    downloads = soup.select(DOWNLOADS_SELECTOR)
    required = ["download=true", "download_filename="]
    default = "mp4", ""
    qualities = {}
    for download in downloads:
        link_str: str = download.get("href")  # type: ignore
        if "/tags/" in link_str or not all(p in link_str for p in required):
            continue
        fmt, res = download.text.rsplit(" ", 1)
        if fmt.lower() not in ("mov", "mp4"):
            continue
        qualities[res] = link_str
        if not default[1]:
            default = res, link_str

    for res in RESOLUTIONS:
        value = qualities.get(res)
        if value:
            return res, value

    return default


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.strptime(date, "%Y-%m-%d")
    return calendar.timegm(parsed_date.timetuple())
