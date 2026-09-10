from __future__ import annotations

import dataclasses
import itertools
import json
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler, DownloadConfig, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, extr_text, json_ld, parse_url
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    PLAYLIST = "script:-soup-contains('window.playlist')"
    VIDEOS = "div#list_videos a.item_link"


@dataclasses.dataclass(slots=True)
class Video:
    id: str
    title: str
    uploaded_at: str

    resolution: Resolution
    content_url: AbsoluteHttpURL
    src: AbsoluteHttpURL


_VIDEO_PER_PAGE = 24


@HTTPConfig(impersonate=True, rate_limit=(1, 3))
@DownloadConfig(slots=2)
class NoodleMagazineCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Search": "/video/<search_query>",
        "Video": "/watch/<video_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://noodlemagazine.com")
    DOMAIN: ClassVar[str] = "noodlemagazine"
    FOLDER_DOMAIN: ClassVar[str] = "NoodleMagazine"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["watch", _]:
                return await self.video(scrape_item)
            case ["video", query]:
                return await self.search(scrape_item, query)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        scrape_item.setup_as_album(self.create_title(f"{query} [search]"))
        init_page = int(scrape_item.url.query.get("p") or 1)
        seen_urls: set[AbsoluteHttpURL] = set()

        for page in itertools.count(1, init_page):
            n_videos = 0
            page_url = scrape_item.url.with_query(p=page)
            soup = await self.request_soup(page_url)

            for new_scrape_item in self.iter_children(scrape_item, soup, Selector.VIDEOS):
                if new_scrape_item.url not in seen_urls:
                    seen_urls.add(new_scrape_item.url)
                    n_videos += 1
                    self.create_task(self.run(new_scrape_item, check_referer=True))

            if n_videos < _VIDEO_PER_PAGE:
                break

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        video = _parse_video(soup)

        scrape_item.uploaded_at = self.parse_iso_date(video.uploaded_at)
        _, ext = self.get_filename_and_ext(filename=video.content_url.name)
        filename = self.create_custom_filename(video.title, ext, file_id=video.id, resolution=video.resolution)
        await self.handle_file(
            video.content_url,
            scrape_item,
            video.title,
            ext,
            custom_filename=filename,
            debrid_link=video.src,
        )


def _parse_video(soup: BeautifulSoup) -> Video:

    _, props = json_ld.find(soup, "contentUrl")

    try:
        playlist_js = css.select_text(soup, Selector.PLAYLIST)
    except css.SelectorError:
        raise ScrapeError(404) from None

    playlist = json.loads(extr_text(playlist_js, "window.playlist = ", ";\nwindow.ads"))

    resolution, src = max(_parse_sources(playlist["sources"]))
    content_url = parse_url(props["contentUrl"])

    return Video(
        title=props["name"],
        uploaded_at=props["uploadDate"],
        content_url=content_url,
        id=content_url.name.removesuffix(content_url.suffix),
        resolution=resolution,
        src=src,
    )


def _parse_sources(sources: list[dict[str, str]]) -> Generator[tuple[Resolution, AbsoluteHttpURL]]:
    for source in sources:
        resolution = Resolution.parse(source["label"])
        yield resolution, parse_url(source["file"])
