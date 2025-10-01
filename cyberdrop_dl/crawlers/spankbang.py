from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, json
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://spankbang.com/")
DEFAULT_QUALITY = "main"
RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
VIDEO_REMOVED_SELECTOR = "[id='video_removed'], [class*='video_removed']"
VIDEOS_SELECTOR = "div.video-list > div.video-item > a"

JS_STREAM_DATA_SELECTOR = "main.main-container > script:-soup-contains('var stream_data')"
JS_VIDEO_INFO_SELECTOR = "main.main-container > script:-soup-contains('uploadDate')"


@dataclass(frozen=True)
class PlaylistInfo:
    id_: str
    url: AbsoluteHttpURL
    title: str = ""

    @classmethod
    def from_url(cls, url: AbsoluteHttpURL, soup: BeautifulSoup | None = None) -> PlaylistInfo:
        playlist_id = url.parts[1].split("-")[0]
        name = url.parts[3]
        canonical_url = PRIMARY_URL / playlist_id / "playlist" / name
        title = css.select_one_get_text(soup, "title").rsplit("Playlist -")[0].strip() if soup else ""
        return cls(playlist_id, canonical_url, title)


class Format(NamedTuple):
    resolution: str
    link_str: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Video:
    id: str
    title: str
    date: str
    best_format: Format


class SpankBangCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Playlist": "/playlist/<playlist-id>",
        "Video": (
            "/video/<video_id>",
            "/embed/<video_id>",
            "/play/<video_id>",
            "/playlist/<playlist-id>-<video_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "spankbang"
    FOLDER_DOMAIN: ClassVar[str] = "SpankBang"

    async def async_startup(self) -> None:
        self.update_cookies({"country": "US", "age_pass": 1})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if _is_playlist(scrape_item.url):
            return await self.playlist(scrape_item)
        if any(p in scrape_item.url.parts for p in ("video", "play", "embed", "playlist")):
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        # Get basic playlist info from the URL
        playlist = PlaylistInfo.from_url(scrape_item.url)
        scrape_item.url = playlist.url
        results = await self.get_album_results(playlist.id_)
        page_url = scrape_item.url
        title: str = ""

        for page in itertools.count(1):
            soup = await self.request_soup(page_url, impersonate=True)

            # Get full playlist info + title from the soup
            playlist = PlaylistInfo.from_url(page_url, soup)
            if not title:
                title = self.create_title(playlist.title, playlist.id_)
                scrape_item.setup_as_album(title, album_id=playlist.id_)

            n_videos = 0

            for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEOS_SELECTOR, results=results):
                n_videos += 1
                self.create_task(self.run(new_scrape_item))

            if n_videos < 100:
                break

            page_url = playlist.url / f"{page + 1}"

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if "playlist" not in scrape_item.url.parts:
            video_id = scrape_item.url.parts[1]
            canonical_url = PRIMARY_URL / video_id / "video"
            if await self.check_complete_from_referer(canonical_url):
                return

        soup = await self.request_soup(scrape_item.url, impersonate=True)
        was_removed = soup.select_one(VIDEO_REMOVED_SELECTOR)
        if was_removed or "This video is no longer available" in soup.text:
            raise ScrapeError(410)

        video = _parse_video(soup)
        canonical_url = PRIMARY_URL / video.id / "video"
        if await self.check_complete_from_referer(canonical_url):
            return
        scrape_item.url = canonical_url
        resolution, link_str = video.best_format
        scrape_item.possible_datetime = self.parse_iso_date(video.date)
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(video.title, ext, file_id=video.id, resolution=resolution)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def _parse_video(soup: BeautifulSoup) -> Video:
    title_tag = css.select_one(soup, "div#video h1")
    stream_js_text = css.select_one_get_text(soup, JS_STREAM_DATA_SELECTOR)
    js_text = css.select_one_get_text(soup, JS_VIDEO_INFO_SELECTOR)
    del soup
    video_data = json.loads(js_text)
    stream_data = json.load_js_obj(get_text_between(stream_js_text, "stream_data = ", ";"))
    embed_url = AbsoluteHttpURL(video_data["embedUrl"])
    return Video(
        id=embed_url.parts[1],
        title=css.get_attr_or_none(title_tag, "title") or css.get_text(title_tag),
        date=video_data["uploadDate"],
        best_format=_get_best_quality(stream_data),
    )


def _get_best_quality(stream_data: dict[str, list[str]]) -> Format:
    """Returns name and URL of the best available quality."""
    for res in RESOLUTIONS:
        if value := stream_data.get(res):
            return Format(res, value[-1])
    raise ScrapeError(422, message="Unable to get download link")


def _is_playlist(url: AbsoluteHttpURL) -> bool:
    return "playlist" in url.parts and "-" not in url.parts[1]
