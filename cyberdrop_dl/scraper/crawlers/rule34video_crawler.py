from __future__ import annotations

import calendar
import json
from datetime import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


RESOLUTIONS = ["4k", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
DOWNLOADS_SELECTOR = "div#tab_video_info div.row_spacer div.wrap > a.tag_item"
JS_SELECTOR = "head > script:contains('uploadDate')"
VIDEO_TITLE_SELECTOR = "h1.title_video"
REQUIRED_FORMAT_STRINGS = "download=true", "download_filename="

PLAYLIST_ITEM_SELECTOR = "div.item.thumb > a.th"
PLAYLIST_NEXT_PAGE_SELECTOR = "div.item.pager.next > a"
PLAYLIST_TITLE_SELECTORS = {
    "tags": "h1.title:contains('Tagged with')",
    "search": "h1.title:contains('Videos for:')",
    "members": "div.channel_logo > h2.title",
    "models": "div.brand_inform > div.title",
}

PLAYLIST_TITLE_SELECTORS["categories"] = PLAYLIST_TITLE_SELECTORS["models"]


class Rule34VideoCrawler(Crawler):
    primary_base_domain = URL("https://rule34video.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34video", "Rule34Video")

    async def async_startup(self) -> None:
        self.set_cookies()

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p in scrape_item.url.parts for p in ("video", "videos")):
            return await self.video(scrape_item)
        if is_playlist(scrape_item.url):
            return await self.playlist(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        added_title = False

        async for soup in self.web_pager(scrape_item):
            if not added_title:
                scrape_item.part_of_album = True
                scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
                title = get_playlist_title(soup, scrape_item.url)
                title = self.create_title(title)
                scrape_item.add_to_parent_title(title)
                added_title = True

            item_tags: list[Tag] = soup.select(PLAYLIST_ITEM_SELECTOR)

            for item in item_tags:
                link_str: str = item.get("href")  # type: ignore
                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        video_id = scrape_item.url.parts[2]
        video_name = scrape_item.url.parts[3]
        canonical_url = self.primary_base_domain / "video" / video_id / video_name / ""

        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
            # soup = get_test_soup()

        scrape_item.url = canonical_url
        info_dict = get_info_dict(soup)
        resolution, link_str = get_best_quality(soup)
        log_debug(json.dumps(info_dict, indent=4))

        link = self.parse_url(link_str)
        log_debug(str(link))

        scrape_item.possible_datetime = parse_datetime(info_dict["uploadDate"])
        name = link.name or link.parent.name
        filename, ext = self.get_filename_and_ext(name)
        custom_filename = link.query.get("download_filename") or info_dict["title"]
        custom_filename = f"{custom_filename} [{video_id}][{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
                # soup = self.client.get_soup_from_file("rule34video_categories.htm")
            next_page = soup.select_one(PLAYLIST_NEXT_PAGE_SELECTOR)
            yield soup
            page_url_str: str = next_page.get("href") if next_page else None  # type: ignore
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str)

    def set_cookies(self) -> None:
        cookies = {"kt_rt_popAccess": 1, "kt_tcookie": 1}
        self.update_cookies(cookies)


def get_info_dict(soup: BeautifulSoup) -> dict:
    title = soup.select_one(VIDEO_TITLE_SELECTOR).text.strip()  # type: ignore
    info_js_script = soup.select_one(JS_SELECTOR)
    info_dict: dict[str, str | dict] = {"title": title.strip()}  # type: ignore
    info_dict = info_dict | javascript.parse_json_to_dict(info_js_script.text)  # type: ignore
    javascript.clean_dict(info_dict)
    return info_dict


def get_best_quality(soup: BeautifulSoup) -> tuple[str, str]:
    """Returns extension and URL of the best available quality.

    Returns URL as `str`"""
    downloads = soup.select(DOWNLOADS_SELECTOR)
    default = "<UNKNOWN>", ""
    qualities = {}
    for download in downloads:
        link_str: str = download.get("href")  # type: ignore
        if "/tags/" in link_str or not all(p in link_str for p in REQUIRED_FORMAT_STRINGS):
            continue
        ext, res = download.text.rsplit(" ", 1)
        if ext.lower() not in ("mov", "mp4"):
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


def get_playlist_title(soup: BeautifulSoup, url: URL) -> str:
    name = get_playlist_type(url)
    assert name
    selector = PLAYLIST_TITLE_SELECTORS.get(name)
    title_tag: Tag = soup.select_one(selector)  # type: ignore
    title = title_tag.text.strip() if title_tag else ""
    if name in ("tags", "search"):
        for span in title_tag.find_all("span"):
            span.decompose()
        title = title_tag.text.split("Tagged with", 1)[-1].split("Videos for:", 1)[-1].strip()  # type: ignore
    return f"{title} [{name}]"


def get_playlist_type(url: URL) -> str:
    for name in PLAYLIST_TITLE_SELECTORS:
        if name in url.parts:
            return name
    return ""


def is_playlist(url: URL) -> bool:
    return bool(get_playlist_type(url))
