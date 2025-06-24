from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    JS = "script:contains('MDCore.ref')"
    FILE_NAME = "div.tbl-c.title b"


_SELECTOR = Selectors()

PRIMARY_URL = AbsoluteHttpURL("https://mixdrop.sb")


class MixDropCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/e/<file_id>",
            "/f/<file_id>",
        )
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "mxdrop", "mixdrop"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "mixdrop"
    FOLDER_DOMAIN: ClassVar[str] = "MixDrop"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in ("f", "e")):
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        file_id = scrape_item.url.name
        video_url = PRIMARY_URL / "f" / file_id
        embed_url = self.get_embed_url(video_url)

        if await self.check_complete_from_referer(embed_url):
            return

        scrape_item.url = embed_url
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, video_url)

        title = css.select_one_get_text(soup, _SELECTOR.FILE_NAME)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, embed_url)

        link = self.create_download_link(soup)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(title, ext)
        await self.handle_file(video_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link)

    @staticmethod
    def create_download_link(soup: BeautifulSoup) -> AbsoluteHttpURL:
        # Defined as a method to simplify subclasses calls
        js_text = css.select_one_get_text(soup, _SELECTOR.JS)
        file_id = get_text_between(js_text, "|v2||", "|")
        parts = get_text_between(js_text, "MDCore||", "|thumbs").split("|")
        secure_key = get_text_between(js_text, f"{file_id}|", "|")
        timestamp = int((datetime.now() + timedelta(hours=1)).timestamp())
        host, ext, expires = ".".join(parts[:-3]), parts[-3], parts[-1]
        url = AbsoluteHttpURL(f"https://s-{host}/v2/{file_id}.{ext}")
        return url.with_query(s=secure_key, e=expires, t=timestamp)

    @staticmethod
    def get_embed_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        return PRIMARY_URL / "e" / url.name
