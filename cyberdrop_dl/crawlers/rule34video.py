from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://rule34video.com/")
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
TITLE_TRASH = "Tagged with", "Videos for:"


@dataclasses.dataclass(frozen=True, slots=True)
class Video:
    title: str
    date: str
    best_src: VideoSource


class VideoSource(NamedTuple):
    ext: str
    resolution: str
    url: str


class Rule34VideoCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Members": "/members/...",
        "Models": "/models/...",
        "Search": "/search/...",
        "Tags": "/tags/...",
        "Video": ("/video/<video_id>/<video_name>", "/videos/<video_id>/<video_name>"),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = PLAYLIST_NEXT_PAGE_SELECTOR
    DOMAIN: ClassVar[str] = "rule34video"
    FOLDER_DOMAIN: ClassVar[str] = "Rule34Video"

    async def async_startup(self) -> None:
        self.update_cookies({"kt_rt_popAccess": 1, "kt_tcookie": 1})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in ("video", "videos")):
            return await self.video(scrape_item)
        if playlist_type := get_playlist_type(scrape_item.url):
            return await self.playlist(scrape_item, playlist_type)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, playlist_type: str) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = get_playlist_title(soup, playlist_type)
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, PLAYLIST_ITEM_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id, video_name = scrape_item.url.parts[2:4]
        canonical_url = PRIMARY_URL / "video" / video_id / video_name / ""

        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        scrape_item.url = canonical_url
        video = _parse_video(soup)
        ext, resolution, link_str = video.best_src
        link = self.parse_url(link_str)
        scrape_item.possible_datetime = self.parse_iso_date(video.date)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = link.query.get("download_filename") or video.title
        custom_filename = self.create_custom_filename(custom_filename, ext, file_id=video_id, resolution=resolution)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def _parse_video(soup: BeautifulSoup) -> Video:
    title = css.select_one_get_text(soup, VIDEO_TITLE_SELECTOR)
    ld_json = css.select_one_get_text(soup, JS_SELECTOR)
    video_data = json.loads(ld_json)
    return Video(title=title, date=video_data["uploadDate"], best_src=_get_best_source(soup))


def _get_available_sources(soup: BeautifulSoup) -> Generator[VideoSource]:
    for download in css.iselect(soup, DOWNLOADS_SELECTOR):
        url = css.get_attr(download, "href")
        if "/tags/" in url or not all(p in url for p in REQUIRED_FORMAT_STRINGS):
            continue
        ext, res = css.get_text(download).rsplit(" ", 1)
        ext = ext.lower()
        if ext not in ("mov", "mp4"):
            continue
        yield VideoSource(ext, res, url)


def _get_best_source(soup: BeautifulSoup) -> VideoSource:
    formats_dict = {v_format.resolution: v_format for v_format in _get_available_sources(soup)}
    for res in RESOLUTIONS:
        if v_format := formats_dict.get(res):
            return v_format
    raise ScrapeError(422, message="Unable to parse video sources")


def get_playlist_title(soup: BeautifulSoup, playlist_type: str) -> str:
    assert playlist_type
    selector = PLAYLIST_TITLE_SELECTORS[playlist_type]
    title_tag = css.select_one(soup, selector)
    if playlist_type in ("tags", "search"):
        for span in title_tag.select("span"):
            span.decompose()

    title = css.get_text(title_tag)
    for trash in TITLE_TRASH:
        title = title.replace(trash, "").strip()

    return f"{title} [{playlist_type}]"


def get_playlist_type(url: AbsoluteHttpURL) -> str:
    return next((name for name in PLAYLIST_TITLE_SELECTORS if name in url.parts), "")
