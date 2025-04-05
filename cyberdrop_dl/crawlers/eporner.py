from __future__ import annotations

import calendar
import json
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING, NamedTuple

from pydantic import ByteSize
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
ALLOW_AV1 = True


DOWNLOADS_SELECTOR = "div#hd-porn-dload > div.dloaddivcol"
VIDEO_SELECTOR = "div[id^='vf'] div.mbcontent a"
PLAYLIST_NEXT_PAGE_SELECTOR = "div.numlist2 a.nmnext"

IMAGES_SELECTOR = "div[id^='pf'] a"
PROFILE_PLAYLIST_SELECTOR = "div.streameventsday.showAll > div#pl > a"

GALLERY_TITLE_SELECTOR = "div#galleryheader"

PROFILE_URL_PARTS = {
    "pics": ("uploaded-pics", IMAGES_SELECTOR),
    "videos": ("uploaded-videos", VIDEO_SELECTOR),
    "playlists": ("playlists", PROFILE_PLAYLIST_SELECTOR),
}


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
    next_page_selector = PLAYLIST_NEXT_PAGE_SELECTOR

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
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        if "profile" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        username = scrape_item.url.parts[2]
        canonical_url = self.primary_base_domain / "profile" / username
        if canonical_url in scrape_item.parents:
            await self.playlist(scrape_item, from_profile=True)
        title = self.create_title(f"{username} [user] ")
        scrape_item.setup_as_profile(title)

        parts_to_scrape = {}
        for name, parts in PROFILE_URL_PARTS.items():
            if any(p in scrape_item.url.parts for p in (name, parts[0])):
                parts_to_scrape = {name: parts}
                break

        parts_to_scrape = parts_to_scrape or PROFILE_URL_PARTS
        for name, parts in parts_to_scrape:
            part, selector = parts
            url = canonical_url / part
            async for soup in self.web_pager(url):
                for _, new_scrape_item in self.iter_items(scrape_item, soup.select(selector), name):
                    self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, from_profile: bool = False) -> None:
        added_title = False

        async for soup in self.web_pager(scrape_item.url):
            if not added_title and not from_profile:
                title = soup.title.text  # type: ignore
                title_trash = "Porn Star Videos", "Porn Videos", "Videos -", "EPORNER"
                for trash in title_trash:
                    title = title.rsplit(trash)[0].strip()
                title = self.create_title(title)
                scrape_item.setup_as_album(title)
                added_title = True

            for _, new_scrape_item in self.iter_items(scrape_item, soup.select(VIDEO_SELECTOR)):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        added_title = False

        async for soup in self.web_pager(scrape_item.url):
            if not added_title:
                title = soup.select_one(GALLERY_TITLE_SELECTOR).get_text(strip=True)  # type: ignore
                title = self.create_title(title)
                scrape_item.setup_as_album(title)
                added_title = True

            for thumb, new_scrape_item in self.iter_items(scrape_item, soup.select(IMAGES_SELECTOR)):
                filename = thumb.name.rsplit("-", 1)[0]
                filename, ext = self.get_filename_and_ext(f"{filename}{thumb.suffix}")
                link = thumb.with_name(filename)
                await self.handle_file(link, new_scrape_item, filename, ext)

    def iter_items(self, scrape_item: ScrapeItem, item_tags: list[Tag], new_title_part: str = ""):
        for item in item_tags:
            link_str: str = item.get("href")  # type: ignore
            link = self.parse_url(link_str)
            thumb_str: str = item.select_one("img").get("src")  # type: ignore
            thumb = self.parse_url(thumb_str)
            yield (thumb, scrape_item.create_child(link, new_title_part=new_title_part))
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

        soup_str = str(soup)
        if "File has been removed due to copyright owner request" in soup_str:
            raise ScrapeError(451)
        if "Video has been deleted" in soup_str:
            raise ScrapeError(410)

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
    info_dict: dict = javascript.parse_json_to_dict(info_js_script.text, use_regex=False)  # type: ignore
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
