from __future__ import annotations

import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from ._chevereto import CheveretoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

PRIMARY_BASE_DOMAIN = URL("https://jpg5.su")
JPG5_REPLACE_HOST_REGEX = re.compile(r"(jpg\.fish/)|(jpg\.fishing/)|(jpg\.church/)")
JPG5_DOMAINS = [
    "jpg5.su",
    "jpg.homes",
    "jpg.church",
    "jpg.fish",
    "jpg.fishing",
    "jpg.pet",
    "jpeg.pet",
    "jpg1.su",
    "jpg2.su",
    "jpg3.su",
    "jpg4.su",
    "host.church",
]


class JPG5Crawler(CheveretoCrawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN
    SUPPORTED_SITES = {"jpg5.su": JPG5_DOMAINS}  # noqa: RUF012

    def __init__(self, manager: Manager, _) -> None:
        super().__init__(manager, "jpg5.su", "JPG5")
        self.request_limiter = AsyncLimiter(1, 5)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem):
        scrape_item.url = scrape_item.url.with_host("jpg5.su")
        return await self._fetch_chevereto_defaults(scrape_item)

    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        raise ValueError

    @error_handling_wrapper
    async def _proccess_media_item(self, scrape_item: ScrapeItem, url_type, *_) -> None:
        """Scrapes a media item."""
        if await self.check_complete_from_referer(scrape_item):
            return

        _, canonical_url = self.get_canonical_url(scrape_item.url, url_type)
        if await self.check_complete_from_referer(canonical_url):
            return

        _, link = await self.get_embed_info(scrape_item.url)
        scrape_item.url = canonical_url
        await self.handle_direct_link(scrape_item, link)

    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None = None) -> None:
        """Handles a direct link."""
        link = url or scrape_item.url
        link = self.parse_url(re.sub(JPG5_REPLACE_HOST_REGEX, r"host.church/", str(link)))
        super().handle_direct_link(scrape_item, link)
