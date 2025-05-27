from __future__ import annotations

import binascii
import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import create_task_id

from ._chevereto import CheveretoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.types import AbsoluteHttpURL

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

DECRYPTION_KEY = b"seltilovessimpcity@simpcityhatesscrapers"


class JPG5Crawler(CheveretoCrawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN
    SUPPORTED_SITES = {"jpg5.su": JPG5_DOMAINS}  # noqa: RUF012

    def __init__(self, manager: Manager, _) -> None:
        super().__init__(manager, "jpg5.su", "JPG5")
        self.request_limiter = AsyncLimiter(1, 5)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem):
        scrape_item.url = fix_host(scrape_item.url)
        return await self._fetch_chevereto_defaults(scrape_item)

    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        raise ValueError

    def parse_url(self, link_str: str, relative_to: URL | None = None, *, trim: bool = True) -> URL:
        if not link_str.startswith("https") and not link_str.startswith("/"):
            link_str = decrypt_xor(link_str, DECRYPTION_KEY)
        return super().parse_url(link_str, relative_to, trim=trim)

    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None = None) -> None:
        """Handles a direct link."""
        link = url or scrape_item.url
        link = fix_host(link)
        await super().handle_direct_link(scrape_item, link)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def fix_host(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    new_host = re.sub(JPG5_REPLACE_HOST_REGEX, r"jpg5.su", f"{url.host}/").removesuffix("/")
    return url.with_host(new_host)


def decrypt_xor(encrypted, key):
    div = len(key)
    encrypted = bytes.fromhex(binascii.a2b_base64(encrypted).decode())
    return bytes([encrypted[i] ^ key[i % div] for i in range(len(encrypted))]).decode()
