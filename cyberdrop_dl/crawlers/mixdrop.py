from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, js_unpacker
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.url_objects import ScrapeItem


class MixDropCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/e/<file_id>",
            "/f/<file_id>",
        )
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "mxdrop", "mixdrop", "m1xdrop"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://mixdrop.sb")
    DOMAIN: ClassVar[str] = "mixdrop"
    FOLDER_DOMAIN: ClassVar[str] = "MixDrop"

    def _prepare_headers(self, scrape_item: ScrapeItem) -> dict[str, str]:
        return super()._prepare_headers(scrape_item) | {"Referer": "https://m1xdrop.click/"}

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["f" | "e", file_id]:
                return await self.file(scrape_item, file_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        embed_url = self.PRIMARY_URL / "e" / file_id
        if await self.check_complete(embed_url):
            return

        scrape_item.url = embed_url
        title, link = await self._request_file_info(file_id)
        filename, ext = self.get_filename_and_ext(title)
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            title,
            ext,
            custom_filename=filename,
            debrid_link=link,
            referer=scrape_item.parents[-1] if scrape_item.parents else scrape_item.url,
        )

    async def _request_file_info(self, file_id: str) -> tuple[str, AbsoluteHttpURL]:
        video_url = self.PRIMARY_URL / "f" / file_id
        embed_url = self.PRIMARY_URL / "e" / file_id

        soup, embed_html = await aio.gather(self.request_soup(video_url), self.request_text(embed_url), fail_fast=False)
        title = css.select_text(soup, "div.tbl-c.title b")
        md_props = dict(_extract_properties(embed_html))
        return title, self.parse_url(md_props["wurl"])


def _extract_properties(html: str) -> Generator[tuple[str, str]]:
    content = js_unpacker.unpack(html)
    for line in content.split(";MDCore."):
        name, _, value = line.partition("=")
        yield name.removeprefix("MDCore."), value.strip('"').strip()
