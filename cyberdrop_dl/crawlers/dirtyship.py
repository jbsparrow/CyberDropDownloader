from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld, parse_url
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    VIDEO = "video#fp-video-0 > source"
    FLOWPLAYER = ".freedomplayer"
    PLAYLIST_ITEM = "li.thumi > a"


class DirtyShipCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Category": "/category/<name>",
        "Tag": "/tag/<name>",
        "Video": "/<slug>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://dirtyship.com")
    NEXT_PAGE_SELECTOR: ClassVar[str] = "a.page-next"
    DOMAIN: ClassVar[str] = "dirtyship"
    FOLDER_DOMAIN: ClassVar[str] = "DirtyShip"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["tag" | "category" as type_, _]:
                return await self.playlist(scrape_item, type_)
            case [_]:
                return await self.video(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, type_: str) -> None:
        soup, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        name = css.select_text(soup, "title").split("Archives", 1)[0]
        title = self.create_title(f"{name} [{type_}]")
        scrape_item.setup_as_album(title)

        async for soup in pages:
            for new_scrape_item in self.iter_children(scrape_item, soup, Selector.PLAYLIST_ITEM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)
        article = json_ld.find_elem(soup, "Article")
        title = css.unescape(article["headline"])
        scrape_item.uploaded_at = self.parse_iso_date(article["datePublished"])

        try:
            resolution, src = max(_parse_flowplayer_sources(soup))
        except css.SelectorError:
            resolution, src = max(_parse_html5_formats(soup))

        filename, ext = self.get_filename_and_ext(src.name)
        custom_filename = self.create_custom_filename(title, ext, resolution=resolution)
        await self.handle_file(
            src,
            scrape_item,
            filename,
            ext,
            custom_filename=custom_filename,
            thumbnail=json_ld.find_elem(soup, "ImageObject")["contentUrl"],
        )


def _parse_html5_formats(soup: BeautifulSoup) -> Generator[tuple[Resolution, AbsoluteHttpURL]]:
    for video in css.iselect(soup, Selector.VIDEO):
        res = Resolution.parse(css.attr(video, "title"))
        link = parse_url(css.attr(video, "src"))
        yield res, link


def _parse_flowplayer_sources(soup: BeautifulSoup) -> Generator[tuple[Resolution, AbsoluteHttpURL]]:
    flow_player = css.select(soup, Selector.FLOWPLAYER, "data-item").replace(r"\/", "/")
    source: dict[str, str]
    for source in json.loads(flow_player)["sources"]:
        yield Resolution.unknown(), parse_url(source["src"])
