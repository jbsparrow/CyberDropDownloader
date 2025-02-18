from __future__ import annotations

import calendar
import json
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING, NamedTuple

from pydantic import ByteSize
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
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


RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
ALLOW_AV1 = True


DOWNLOADS_SELECTOR = "div#hd-porn-dload > div.dloaddivcol"
PLAYLIST_ITEM_SELECTOR = "div[id^='vidresults'] > div[id^='vf'] div.mbcontent a"
PLAYLIST_NEXT_PAGE_SELECTOR = "div.numlist2 a.nmnext"


class VideoInfo(NamedTuple):
    codec: str  # av1 > h264
    resolution: str
    size: str
    link_str: str

    @cached_property
    def byte_size(self) -> ByteSize:
        return ByteSize(self.size)

    @classmethod
    def from_tag(cls, tag: Tag) -> VideoInfo:
        link_str: str = tag.get("href")  # type: ignore
        name = tag.get_text()
        name_string = name.removeprefix("Download").strip()
        details = name_string.split("(", 1)[1].removesuffix(")").split(",")
        res, codec, size = tuple([d.strip() for d in details])
        codec = codec.lower()
        return cls(codec, res, size, link_str)


class EpornerCrawler(Crawler):
    primary_base_domain = URL("https://www.eporner.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "eporner", "ePorner")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if get_video_id(scrape_item.url):
            return await self.video(scrape_item)
        if any(p in scrape_item.url.parts for p in ("cat", "channel", "search", "pornstar")):
            return await self.playlist(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        added_title = False

        async for soup in self.web_pager(scrape_item):
            if not added_title:
                scrape_item.part_of_album = True
                scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
                title = soup.title.text  # type: ignore
                title_trash = "Porn Star Videos", "Porn Videos", "Videos -", "EPORNER"
                for trash in title_trash:
                    title = title.rsplit(trash)[0].strip()
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
        """Scrapes an embeded video page."""
        video_id = get_video_id(scrape_item.url)
        canonical_url = self.primary_base_domain / f"video-{video_id}"

        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.url = canonical_url
        info_dict = get_info_dict(soup)
        log_debug(json.dumps(info_dict, indent=4))
        resolution, link_str = get_best_quality(soup)
        if not link_str:
            raise ScrapeError(422, origin=scrape_item)

        link = self.parse_url(link_str)
        date = parse_datetime(info_dict["uploadDate"])
        scrape_item.possible_datetime = date
        filename, ext = self.get_filename_and_ext(link.name)
        if ext == ".m3u8":
            raise ScrapeError(422, origin=scrape_item)
        custom_filename = f"{info_dict['name']} [{video_id}][{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select_one(PLAYLIST_NEXT_PAGE_SELECTOR)
            yield soup
            page_url_str: str = next_page.get("href") if next_page else None  # type: ignore
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str)


def get_available_resolutions(soup: BeautifulSoup) -> list[VideoInfo]:
    downloads = soup.select_one(DOWNLOADS_SELECTOR)
    assert downloads
    formats = downloads.select("span.download-h264 > a")
    if ALLOW_AV1:
        av1_formats = downloads.select("span.download-av1 > a")
        formats.extend(av1_formats)
    return [VideoInfo.from_tag(tag) for tag in formats]


def get_best_quality(soup: BeautifulSoup) -> tuple[str, str]:
    """Returns name and URL of the best available quality.

    Returns URL as `str`"""
    formats = get_available_resolutions(soup)
    best_format = formats[0]
    formats_dict: dict[str, list[VideoInfo]] = {}
    for res in RESOLUTIONS:
        formats_dict[res] = sorted(f for f in formats if f.resolution == res)

    log_debug(json.dumps(formats_dict, indent=4))

    for res in RESOLUTIONS:
        available_formats = formats_dict.get(res)
        if available_formats:
            best_format = available_formats[0]
            break

    return best_format.resolution, best_format.link_str


def get_info_dict(soup: BeautifulSoup) -> dict:
    info_js_script = soup.select_one("main script:contains('uploadDate')")
    info_dict = javascript.parse_json_to_dict(info_js_script.text, use_regex=False)  # type: ignore
    javascript.clean_dict(info_dict)
    return info_dict


def get_video_id(url: URL) -> str:
    if "video-" in url.parts[1]:
        return url.parts[1].rsplit("-", 1)[1]
    if any(p in url.parts for p in ("hd-porn", "embed")) and len(url.parts) > 2:
        return url.parts[2]
    return ""


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.fromisoformat(date)
    return calendar.timegm(parsed_date.timetuple())
