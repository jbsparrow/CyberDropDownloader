from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, parse_url
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class MultPornCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "comic": (
            "/comics/<slug>",
            "/hentai_manga/<slug>",
            "/humor/<slug>",
            "/gay_porn_comics/<slug>",
        ),
        "video": "/video/<slug>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://multporn.net")
    DOMAIN: ClassVar[str] = "multporn.net"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["comics" | "hentai_manga" | "gay_porn_comics" | "humor", _]:
                return await self.comic(scrape_item)
            case ["video", _]:
                return await self.video(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def comic(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)
        name, date = _extract_info(soup)
        scrape_item.uploaded_at = self.parse_iso_date(date)
        scrape_item.setup_as_album(self.create_title(name))
        async with self.new_task_group() as tg:
            for img in _extract_images(soup):
                tg.create_task(self.direct_file(scrape_item, img))
                scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)
        name, date = _extract_info(soup)
        scrape_item.uploaded_at = self.parse_iso_date(date)
        filename = self.create_custom_filename(name, ext := ".mp4")
        src = css.select(soup, ".content video source", "src")
        await self.handle_file(self.parse_url(src), scrape_item, name, ext, custom_filename=filename)


def _extract_images(soup: BeautifulSoup) -> Generator[AbsoluteHttpURL]:
    subpath = "/styles/juicebox_medium/public/"
    for img in css.iselect(soup, ".content .jb-image img", "src"):
        url = parse_url(img)
        path = url.path.replace(subpath, "/")
        yield url.with_path(path)


def _extract_info(soup: BeautifulSoup) -> tuple[str, str]:
    name = css.select_text(soup, "h1#page-title")
    date = css.select(soup, "meta[name='dcterms.date']", "content")
    return name, date
