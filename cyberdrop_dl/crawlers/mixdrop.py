from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


JS_SELECTOR = "script:contains('MDCore.ref')"
FILE_NAME_SELECTOR = "div.tbl-c.title b"


class MixDropCrawler(Crawler):
    primary_base_domain = URL("https://mixdrop.sb")

    def __init__(self, manager: Manager) -> None:
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
        canonical_url = self.primary_base_domain / "f" / file_id
        embed_url = self.primary_base_domain / "e" / file_id

        if await self.check_complete_from_referer(canonical_url):
            return

        scrape_item.url = canonical_url
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, canonical_url)

        title = soup.select_one(FILE_NAME_SELECTOR).get_text(strip=True)  # type: ignore

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, embed_url)

        link = create_download_link(soup)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename, _ = self.get_filename_and_ext(title)
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
        )


def create_download_link(soup: BeautifulSoup) -> URL:
    js_text = soup.select_one(JS_SELECTOR).text  # type: ignore
    file_id = get_text_between(js_text, "|v2||", "|")
    parts = get_text_between(js_text, "MDCore||", "|thumbs").split("|")
    secure_key = get_text_between(js_text, f"{file_id}|", "|")
    timestamp = int((datetime.now() + timedelta(hours=1)).timestamp())
    host, ext, expires = ".".join(parts[:-3]), parts[-3], parts[-1]
    return URL(f"https://s-{host}/v2/{file_id}.{ext}").with_query(s=secure_key, e=expires, t=timestamp)
