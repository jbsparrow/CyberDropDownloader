from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, ClassVar, Self, final

from cyberdrop_dl import aio
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler, URLConfig
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


@final
class Selector:
    UPLOAD_DATE = "span.hidden.sm\\:inline"
    ALBUM_FILES = "a[\\:href*='javascript:void(0)']", ":href"
    USER_FILES = "a.group.relative[href]"
    NEXT_PAGE = "a[rel=next]"
    ARCHIVE = "[x-data='archiveViewer()']"
    DIRECT_DL = "#embed-direct"
    EMBED = ".embed-link a[href]"


@dataclasses.dataclass(slots=True)
class File:
    name: str
    mime: str | None
    uploaded_at: str
    assume_ext: str
    source: str
    is_archive: bool

    @classmethod
    def parse(cls, soup: BeautifulSoup) -> Self:
        og = open_graph.parse(soup)
        mimetype = None
        is_archive = bool(soup.select_one(Selector.ARCHIVE))

        if is_archive:
            assume_ext, source = ".zip", css.select(soup, Selector.DIRECT_DL, "value")
        elif og.video:
            assume_ext, mimetype, source = ".mp4", og.video_type, og.video
        else:
            assume_ext, source = ".jpg", og.image

        return cls(
            name=og.title,
            mime=mimetype,
            uploaded_at=css.select_text(soup, Selector.UPLOAD_DATE),
            assume_ext=assume_ext,
            source=source,
            is_archive=is_archive,
        )


@HTTPConfig(rate_limit=(2, 1))
@URLConfig(trim=False)
class ImagePondCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "Image / Video / Archive": (
            "/i/<slug>",
            "/img/<slug>",
            "/image/<slug>",
            "/video/<slug>",
            "/videos/<slug>",
        ),
        "Album": "/a/<slug>",
        "User": (
            "/user/<user_name>",
            "/<user_name>",
        ),
        "Direct links": "/media/<slug>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.imagepond.net")
    DOMAIN: ClassVar[str] = "imagepond.net"
    FOLDER_DOMAIN: ClassVar[str] = "ImagePond"
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["i" | "img" | "image" | "video", _]:
                await self.file(scrape_item)
            case ["a", _]:
                await self.album(scrape_item)
            case ["media", _, *_] if self.is_subdomain(scrape_item.url):
                await self.direct_file(scrape_item)
            case ["user", user_name] | [user_name]:
                await self.user(scrape_item, user_name)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        match url.parts[1:]:
            case ["videos", slug] | ["i", slug, *_]:
                return url.origin() / "i" / slug
            case [a, b, "download", *_]:
                return url.origin() / a / b
            case _:
                return url

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request(scrape_item.url) as resp:
            if resp.url != scrape_item.url:
                with scrape_item.track_changes:
                    scrape_item.url = resp.url
                if await self.check_complete_from_referer(resp.url):
                    return

            soup = await resp.soup()

        try:
            file = File.parse(soup)
        except (css.SelectorError, open_graph.OpenGraphError):
            if embed := soup.select_one(Selector.EMBED):
                scrape_item.url = self.parse_url(css.attr(embed, "href"))
                self.create_task(self.run(scrape_item))
                return
            raise

        await self._file(scrape_item, file)

    async def _file(self, scrape_item: ScrapeItem, file: File) -> None:
        scrape_item.uploaded_at = self.parse_date(file.uploaded_at, "%b %d, %Y")
        filename, ext = self.get_filename_and_ext(file.name, assume_ext=file.assume_ext, mime_type=file.mime)
        await self.handle_file(
            self.parse_url(file.source),
            scrape_item,
            file.name,
            ext,
            custom_filename=filename,
        )

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        soup, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        title = css.select_text(soup, "h1")
        scrape_item.setup_as_album(self.create_title(title), album_id=scrape_item.url.name)

        async for soup in pages:
            for js in css.iselect(soup, *Selector.ALBUM_FILES):
                web_url = js[js.index("'http") :].strip("'")
                new_item = scrape_item.create_child(self.parse_url(web_url))
                self.create_task(self.run(new_item, check_referer=True))
                scrape_item.add_children()

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, user_name: str) -> None:
        title = self.create_title(f"{user_name} [user]")
        scrape_item.setup_as_profile(title)

        async for soup in self.web_pager(scrape_item.url):
            for new_item in self.iter_children(scrape_item, soup, Selector.USER_FILES):
                self.create_task(self.run(new_item))
