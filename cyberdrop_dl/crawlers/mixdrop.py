from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


JS_SELECTOR = "script:contains('MDCore.ref')"


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
        canonical_url = self.primary_base_domain / "e" / file_id

        if self.check_complete_from_referer(canonical_url):
            return

        scrape_item.url = canonical_url
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, canonical_url)

        js_text = soup.select_one(JS_SELECTOR).text  # type: ignore
        parts = get_text_between(js_text, "MDCore||", "|thumbs").split("|")
        expires = parts[-1]
        secure_key, timestamp = get_text_between(js_text, f"{file_id}|", "|_t").split("|")
        host = ".".join(parts[:-3])
        link = self.parse_url(f"https://s-{host}/v2/{file_id}.mp4").with_query(s=secure_key, e=expires, t=timestamp)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(canonical_url, scrape_item, filename, ext, debrid_link=link)
