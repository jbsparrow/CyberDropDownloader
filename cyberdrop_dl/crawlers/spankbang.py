from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, ClassVar, final

from cyberdrop_dl import aio
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils import css, extr_text, json
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


@final
class Selector:
    STREAM_DATA = ".main-container script:-soup-contains('var stream_data')"
    PLAYLIST_TITLE = "[data-testid=playlist-title]"
    NEXT_PAGE = ".pagination li.next > a[href]"

    VIDEO_REMOVED = "#video_removed, .video_removed"
    _playlist, _video = ".js-video-item > a[href*='/playlist/']", ".js-video-item > a[href*='/video/']"
    VIDEOS = ", ".join(
        (
            "#search_v2 " + _playlist,
            "#search_v2 " + _video,
            "#search_page " + _playlist,
            "#search_page " + _video,
        )
    )


@dataclasses.dataclass(slots=True)
class Video:
    id: str
    stream_id: str
    stream_key: str
    title: str
    resolution: Resolution
    url: str


@HTTPConfig(impersonate=True, rate_limit=(2, 5))
class SpankBangCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Playlist": "/<playlist_id>/playlist/...",
        "Profile": (
            "/profile/<user>",
            "/profile/<user>/videos",
        ),
        "Video": (
            "/<video_id>/video",
            "/<video_id>/embed",
            "/play/<video_id>",
            "<playlist_id>-<video_id>/playlist/...",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://spankbang.com")
    DOMAIN: ClassVar[str] = "spankbang"
    FOLDER_DOMAIN: ClassVar[str] = "SpankBang"
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def __async_post_init__(self) -> None:
        self.update_cookies({"country": "US", "age_pass": 1})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [playlist_id, "playlist", _, _page]:
                return await self.playlist(scrape_item, playlist_id)
            case [video_id, "video" | "embed" | "play", *_]:
                return await self.video(scrape_item, video_id)
            case ["profile", user, "videos"]:
                return await self.profile(scrape_item, user)
            case ["s", query, *_]:
                return await self.search(scrape_item, query)
            case [id_, "playlist", _]:
                playlist_id, _, video_id = id_.partition("-")
                if video_id:
                    return await self.video(scrape_item, video_id)
                return await self.playlist(scrape_item, playlist_id)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url).with_host(cls.PRIMARY_URL.host)
        match url.parts[1:]:
            case ["profile", _]:
                return url / "videos"
            case _:
                return url

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        # old referer logic. video_id may be canonical (unique per video) or relative (different on each playlist)
        old_db_url = self.PRIMARY_URL / video_id / "video"
        if await self.check_complete_from_referer(old_db_url):
            return

        async with self.request(scrape_item.url, impersonate=True) as resp:
            if await self.check_complete_from_referer(resp.url):
                return

            if "video" not in resp.url.parts:
                raise ScrapeError(404)

            scrape_item.url = resp.url
            video_id = resp.url.parts[1]
            video = _parse_video(await resp.soup(), video_id)

        old_db_url2 = self.PRIMARY_URL / video.stream_id / "video"
        if old_db_url2 != old_db_url and await self.check_complete_from_referer(old_db_url2):
            return

        link = self.parse_url(video.url)
        _, ext = self.get_filename_and_ext(link.name)
        filename = self.create_custom_filename(video.title, ext, file_id=video.id, resolution=video.resolution)
        await self.handle_file(link, scrape_item, video.title, ext, custom_filename=filename, metadata=video)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, playlist_id: str) -> None:
        soup, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        name = css.select_text(soup, Selector.PLAYLIST_TITLE)
        if (trash := name.casefold().rfind(" playlist")) != -1:
            name = name[:trash].strip()

        title = self.create_title(f"{name} [playlist]", playlist_id)
        scrape_item.setup_as_album(title, album_id=playlist_id)

        async for soup in pages:
            await self._iter_videos(scrape_item, soup)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        scrape_item.setup_as_album(self.create_title(f"{query} [search]"))
        async for soup in self.web_pager(scrape_item.url):
            await self._iter_videos(scrape_item, soup)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem, user: str) -> None:
        scrape_item.setup_as_profile(self.create_title(f"{user} [user]"))
        async for soup in self.web_pager(scrape_item.url):
            await self._iter_videos(scrape_item, soup)

    async def _iter_videos(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        async with self.new_task_group() as tg:
            for new_item in self.iter_children(scrape_item, soup, Selector.VIDEOS):
                tg.create_task(self.run(new_item, check_referer=True))


def _parse_video(soup: BeautifulSoup, display_id: str) -> Video:
    # The title of the video is localized
    # soup should be from the main english site
    if soup.select_one(Selector.VIDEO_REMOVED) or "This video is no longer available" in soup.get_text():
        raise ScrapeError(410)

    title_tag = css.select(soup, "div#video h1")
    stream_js_text = css.select_text(soup, Selector.STREAM_DATA)
    stream_data = extr_text(stream_js_text, "stream_data = ", ";")
    res, url = max(_parse_formats(stream_data))
    return Video(
        id=display_id,
        resolution=res,
        url=url,
        stream_id=extr_text(stream_js_text, "ana_video_id = ", ";").strip("'"),
        stream_key=css.select(soup, "[data-streamkey]", "data-streamkey"),
        title=css.attr_or_none(title_tag, "title") or css.text(title_tag),
    )


def _parse_formats(stream_data: str) -> Generator[tuple[Resolution, str]]:
    formats: dict[str, list[str]] = json.load_js_obj(stream_data)
    for name, options in formats.items():
        if not options or "m3u8" in name:
            continue

        try:
            resolution = Resolution.parse(name)
        except ValueError:
            continue

        yield resolution, options[-1]
