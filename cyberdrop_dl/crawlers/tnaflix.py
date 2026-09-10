from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl import aio
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld, open_graph
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    VIDEO_SRC = "video#video-player source"
    COLLECTION_TITLE = "div.ph-title > h1"
    VIDEOS_THUMBS = "div.video-list a.video-thumb"
    NEXT_PAGE = "li.pagination-next > a"


class Format(NamedTuple):
    resolution: Resolution
    link_str: str


@HTTPConfig(rate_limit=(3, 10))
class TNAFlixCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/<category>/<title>/video<video_id>",
        "Channel": "/channel/...",
        "Profile": "/profile/...",
        "Search": "/search?what=<query>",
    }
    DOMAIN: ClassVar[str] = "tnaflix"
    FOLDER_DOMAIN: ClassVar[str] = "TNAFlix"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.tnaflix.com")
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_, _, name] if name.startswith("video") and (video_id := name.removeprefix("video")):
                return await self.video(scrape_item, video_id)
            case ["search" as type_] if query := scrape_item.url.query.get("what"):
                return await self.collection(scrape_item, type_, query)
            case ["channel" | "profile" as type_, _]:
                return await self.collection(scrape_item, type_)
            case _:
                raise ValueError

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
        return await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: str, name: str | None = None) -> None:
        soup, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        name = name or css.select_text(soup, Selector.COLLECTION_TITLE)
        title = self.create_title(f"{name} - [{collection_type}]")
        scrape_item.setup_as_album(title)

        async for soup in pages:
            for new_scrape_item in self.iter_children(scrape_item, soup, Selector.VIDEOS_THUMBS):
                self.create_task(self.run(new_scrape_item, check_referer=True))


def _parse_formats(soup: BeautifulSoup) -> Generator[Format]:
    for src in soup.select(Selector.VIDEO_SRC):
        url = css.attr(src, "src")
        resolution = Resolution.parse(css.attr(src, "size"))
        yield Format(resolution, url)
