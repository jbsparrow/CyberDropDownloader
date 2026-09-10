from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld, open_graph, parse_url
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class NaughtyMachinimaCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/video/<video_id>",
        "Album": "/album/<album_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.naughtymachinima.com")
    NEXT_PAGE_SELECTOR: ClassVar[str] = ".pagination li:has(.fa-caret-right) a"
    DOMAIN: ClassVar[str] = "naughtymachinima"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["video", video_id, *_]:
                return await self.video(scrape_item, video_id)
            case ["album", album_id, *_]:
                return await self.album(scrape_item, album_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        name = open_graph.title(soup)
        scrape_item.uploaded_at = json_ld.upload_date(soup)
        res, src = max(_extract_sources(soup))
        filename = self.create_custom_filename(name, ext := ".mp4", resolution=res, file_id=video_id)
        await self.handle_file(src, scrape_item, name, ext, custom_filename=filename)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        first_page, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        name = css.select_text(first_page, "title").rpartition(" Gallery - Naughty Machinima")[0]
        title = self.create_title(name, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        should_download = await self.make_album_checker(album_id)

        async for soup in pages:
            for photo in filter(should_download, _extract_photos(soup)):
                self.create_eager_task(self.direct_file(scrape_item, photo))
                scrape_item.add_children()


def _extract_sources(soup: BeautifulSoup) -> Generator[tuple[int, AbsoluteHttpURL]]:
    for src in css.iselect(soup, "video#vjsplayer source"):
        res = int(css.attr(src, "res"))
        url = parse_url(css.attr(src, "src"))
        yield res, url


def _extract_photos(soup: BeautifulSoup) -> Generator[AbsoluteHttpURL]:
    for thumb in css.iselect(soup, "img[id^='album_photo_']", "src"):
        url = thumb.replace("/tmb/", "/")
        yield parse_url(url)
