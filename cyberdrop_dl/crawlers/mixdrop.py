from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class Selectors:
    JS = "script:contains('MDCore.ref')"
    FILE_NAME = "div.tbl-c.title b"


_SELECTOR = Selectors()

PRIMARY_BASE_DOMAIN = URL("https://mixdrop.sb")


class MixDropCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"mixdrop": ["mxdrop", "mixdrop"]}
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager, *_) -> None:
        super().__init__(manager, "mixdrop", "MixDrop")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p in scrape_item.url.parts for p in ("f", "e")):
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        file_id = scrape_item.url.name
        video_url = self.primary_base_domain / "f" / file_id
        embed_url = self.get_embed_url(video_url)

        if await self.check_complete_from_referer(embed_url):
            return

        scrape_item.url = embed_url
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, video_url)

        title = soup.select_one(_SELECTOR.FILE_NAME).get_text(strip=True)  # type: ignore

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, embed_url)

        link = self.create_download_link(soup)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename, _ = self.get_filename_and_ext(title)
        await self.handle_file(video_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link)

    @staticmethod
    def create_download_link(soup: BeautifulSoup) -> URL:
        # Defined as a method to simplify subclasses calls
        js_text = soup.select_one(_SELECTOR.JS).text  # type: ignore
        file_id = get_text_between(js_text, "|v2||", "|")
        parts = get_text_between(js_text, "MDCore||", "|thumbs").split("|")
        secure_key = get_text_between(js_text, f"{file_id}|", "|")
        timestamp = int((datetime.now() + timedelta(hours=1)).timestamp())
        host, ext, expires = ".".join(parts[:-3]), parts[-3], parts[-1]
        return URL(f"https://s-{host}/v2/{file_id}.{ext}").with_query(s=secure_key, e=expires, t=timestamp)

    @staticmethod
    def get_embed_url(url: URL) -> URL:
        return PRIMARY_BASE_DOMAIN / "e" / url.name
