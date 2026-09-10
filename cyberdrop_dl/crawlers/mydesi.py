from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class MyDesiCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "fry99.com", "lolpol.com", "mydesi.net"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Videos": "/title",
        "Search": "/search/<query>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://lolpol.com")
    DOMAIN: ClassVar[str] = "mydesi.net"
    FOLDER_DOMAIN: ClassVar[str] = "MyDesi"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["search", query, *rest]:
                match rest:
                    case ["page", init_page]:
                        init_page = int(init_page)
                    case _:
                        init_page = 1
                return await self.search(scrape_item, query, init_page)

            case [_]:
                return await self.video(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return None

        soup = await self.request_soup(scrape_item.url)
        resolution, link = max(_parse_formats(soup))
        link = self.parse_url(link)
        _, ext = self.get_filename_and_ext(link.name)
        metadata: dict[str, Any] = json_ld.find_attr(soup, "subjectOf")
        title = metadata["name"]

        scrape_item.uploaded_at = self.parse_iso_date(metadata["uploadDate"])
        custom_filename = self.create_custom_filename(title, ext, resolution=resolution)
        return await self.handle_file(link, scrape_item, title, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str, init_page: int = 1) -> None:
        title = self.create_title(f"{query} [search]")
        scrape_item.setup_as_album(title)

        base_url = scrape_item.url.origin() / "search" / query / "page"
        for page in itertools.count(init_page):
            soup = await self.request_soup(base_url / str(page))
            n_videos = 0
            for new_scrape_item in self.iter_children(scrape_item, soup, "a.infos"):
                n_videos += 1
                self.create_task(self.run(new_scrape_item))

            if n_videos < 38:
                break


def _parse_formats(soup: BeautifulSoup) -> Generator[tuple[Resolution, str]]:
    for src in soup.select("#video-rate > a"):
        quality = css.attr(src, "title")
        link = css.attr(src, "href")
        resolution = Resolution.highest() if "original" in quality.casefold() else Resolution.parse(quality)
        yield resolution, link
