from __future__ import annotations

import calendar
from datetime import datetime
from typing import TYPE_CHECKING, NamedTuple

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.data_structures.url_objects import ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
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


class Format(NamedTuple):
    ext: str
    resolution: str
    link_str: str


## TODO: convert to global dataclass with constructor from dict to use in multiple crawlers
class VideoInfo(dict): ...


class Rule34VideoCrawler(Crawler):
    primary_base_domain = URL("https://rule34video.com/")
    next_page_selector = PLAYLIST_NEXT_PAGE_SELECTOR

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
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = get_playlist_title(soup, scrape_item.url)
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, PLAYLIST_ITEM_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        video_id, video_name = scrape_item.url.parts[2:4]
        canonical_url = self.primary_base_domain / "video" / video_id / video_name / ""

        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        scrape_item.url = canonical_url
        info = get_video_info(soup)
        v_format = get_best_quality(soup)
        if not v_format:
            raise ScrapeError(422)
        ext, resolution, link_str = v_format
        link = self.parse_url(link_str)
        scrape_item.possible_datetime = parse_datetime(info["uploadDate"])

        name = link.name or link.parent.name
        filename, ext = self.get_filename_and_ext(name)
        custom_filename = link.query.get("download_filename") or info["title"]
        custom_filename, _ = self.get_filename_and_ext(f"{custom_filename} [{video_id}][{resolution}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    def set_cookies(self) -> None:
        cookies = {"kt_rt_popAccess": 1, "kt_tcookie": 1}
        self.update_cookies(cookies)


def get_video_info(soup: BeautifulSoup) -> VideoInfo:
    title = soup.select_one(VIDEO_TITLE_SELECTOR).text.strip()  # type: ignore
    info_js_script = soup.select_one(JS_SELECTOR)
    info: dict[str, str | dict] = javascript.parse_json_to_dict(info_js_script.text)  # type: ignore
    info["title"] = title
    javascript.clean_dict(info)
    log_debug(info)
    return VideoInfo(**info)


def get_available_formats(soup: BeautifulSoup) -> Generator[Format]:
    for download in soup.select(DOWNLOADS_SELECTOR):
        link_str: str = download.get("href")  # type: ignore
        if "/tags/" in link_str or not all(p in link_str for p in REQUIRED_FORMAT_STRINGS):
            continue
        ext, res = download.text.rsplit(" ", 1)
        ext = ext.lower()
        if ext not in ("mov", "mp4"):
            continue
        yield Format(ext, res, link_str)


def get_best_quality(soup: BeautifulSoup) -> Format | None:
    formats_dict = {v_format.resolution: v_format for v_format in get_available_formats(soup)}
    log_debug(formats_dict)
    for res in RESOLUTIONS:
        v_format = formats_dict.get(res)
        if v_format:
            return v_format


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
    return next((name for name in PLAYLIST_TITLE_SELECTORS if name in url.parts), "")


def is_playlist(url: URL) -> bool:
    return bool(get_playlist_type(url))
