from __future__ import annotations

import binascii
import re
from functools import partialmethod
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from ._chevereto import CheveretoCrawler, Media

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

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

IMAGE_SELECTOR = "div.image-viewer-main > img"
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
        scrape_item.url = scrape_item.url.with_host("jpg5.su")
        return await self._fetch_chevereto_defaults(scrape_item)

    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        raise ValueError

    @error_handling_wrapper
    async def _proccess_media_item(self, scrape_item: ScrapeItem, media_type: Media, selector: tuple[str, str]) -> None:
        """Scrapes a media item."""
        if await self.check_complete_from_referer(scrape_item):
            return
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        img_tag = soup.select_one(IMAGE_SELECTOR)
        if not img_tag:
            raise ScrapeError(404)
        direct_link = self.parse_url(decrypt_xor(img_tag["data-src"], DECRYPTION_KEY))
        await self.handle_direct_link(scrape_item, direct_link)

    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None = None) -> None:
        """Handles a direct link."""
        link = url or scrape_item.url
        link = self.parse_url(re.sub(JPG5_REPLACE_HOST_REGEX, r"host.church/", str(link)))
        await super().handle_direct_link(scrape_item, link)

    image = partialmethod(_proccess_media_item, media_type=Media.IMAGE, selector=IMAGE_SELECTOR)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def decrypt_xor(encrypted, key):
    div = len(key)
    encrypted = bytes.fromhex(binascii.a2b_base64(encrypted).decode())
    return bytes([encrypted[i] ^ key[i % div] for i in range(len(encrypted))]).decode()
