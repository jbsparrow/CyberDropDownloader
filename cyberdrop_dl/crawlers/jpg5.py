from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from ._chevereto import CheveretoCrawler

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

JPG5_REPLACE_HOST_REGEX = re.compile(r"(jpg\.fish/)|(jpg\.fishing/)|(jpg\.church/)")


class JPG5Crawler(CheveretoCrawler):
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {
        "Album": "/a/...",
        "Image": "/img/...",
        "Profiles": "/...",
        "Direct links": "",
    }

    SUPPORTED_HOSTS = (
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
    )
    DOMAIN = "jpg5.su"
    FOLDER_DOMAIN = "JPG5"

    primary_base_domain = AbsoluteHttpURL("https://jpg5.su")

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(1, 5)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = scrape_item.url.with_host("jpg5.su")
        return await self._fetch_chevereto_defaults(scrape_item)

    async def video(self, scrape_item: ScrapeItem) -> None:
        raise ValueError

    @error_handling_wrapper
    async def _proccess_media_item(self, scrape_item: ScrapeItem, url_type, *_) -> None:
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
        await super().handle_direct_link(scrape_item, link)
