from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl import aio
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.utils import css, json_ld, open_graph
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    VIDEO_SRC = ".gif-video, #main_video source"
    COLLECTION_TITLE = "h2.object-title"
    SEARCH_VIDEOS = "div.list-videos div.item > a"
    NEXT_PAGE = "div.pagination-holder li.next > a"


class Format(NamedTuple):
    resolution: Resolution
    link_str: str


@HTTPConfig(rate_limit=(3, 10))
class FluidPlayerCrawler(Crawler, is_abc=True):
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return None

        soup = await self.request_soup(scrape_item.url)
        best_format = max(_parse_formats(soup))
        link = self.parse_url(best_format.link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        title = open_graph.title(soup)
        scrape_item.uploaded_at = json_ld.upload_date(soup)
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id, resolution=best_format.resolution)
        return await self.handle_file(
            scrape_item.url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
        )

    @error_handling_wrapper
    async def collection(
        self,
        scrape_item: ScrapeItem,
        collection_type: str,
        name: str | None = None,
    ) -> None:
        soup, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        name = name or css.select_text(soup, Selector.COLLECTION_TITLE)
        title = self.create_title(f"{name} [{collection_type}]")
        scrape_item.setup_as_album(title)

        async for soup in pages:
            for new_item in scrape_item.create_children(self.iter_urls(soup, Selector.SEARCH_VIDEOS)):
                self.create_task(self.run(new_item, check_referer=True))


def _parse_formats(soup: BeautifulSoup) -> Generator[Format]:
    parse_resolution = Resolution.make_parser()
    for src in css.iselect(soup, Selector.VIDEO_SRC):
        url = css.attr(src, "src")
        quality = css.attr_or_none(src, "title")
        resolution = parse_resolution(quality)
        yield Format(resolution, url)
