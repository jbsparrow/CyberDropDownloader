from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class SuvoboxCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/<album_id>",
        "File": ("/f/<file_id>",),
        "Direct File": (
            "/m/<file_id>-medium.<ext>",
            "/d/<file_id>.<ext>",
        ),
    }

    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.suvobox.com")
    DOMAIN: ClassVar[str] = "suvobox"
    NEXT_PAGE_SELECTOR: ClassVar[str] = "a.pager-btn:-soup-contains-own(Next)"

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url).without_query_params("album")
        match url.parts[1:]:
            case ["m" | "d", slug] if "media." in url.host:
                file_id = slug.partition("-")[0].partition(".")[0]
                return cls.PRIMARY_URL / "f" / file_id
            case _:
                return url

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["f", _file_id]:
                await self.file(scrape_item)
            case ["a", album_id]:
                await self.album(scrape_item, album_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        soup, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        name = open_graph.title(soup)
        scrape_item.setup_as_album(self.create_title(name, album_id), album_id=album_id)
        async for soup in pages:
            for item in self.iter_children(scrape_item, soup, "a.thumb-item"):
                self.create_task(self.run(item, check_referer=True))
                scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        src = self.parse_url(css.select(soup, "a[href*=token]:-soup-contains-own('⬇ Download')", "href"))

        name = open_graph.title(soup)
        thumb = open_graph.get_image(soup)
        filename, ext = self.get_filename_and_ext(name, assume_ext=".mp4")
        await self.handle_file(
            src,
            scrape_item,
            name,
            ext,
            custom_filename=filename,
            thumbnail=thumb if thumb != "https://media.suvobox.com/t/" else None,
        )
