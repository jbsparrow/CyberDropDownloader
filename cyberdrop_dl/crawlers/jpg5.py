from __future__ import annotations

import binascii
import re
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.types import AbsoluteHttpURL, SupportedDomains, SupportedPaths

from ._chevereto import CheveretoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

JPG5_REPLACE_HOST_REGEX = re.compile(r"(jpg\.fish/)|(jpg\.fishing/)|(jpg\.church/)")
DECRYPTION_KEY = b"seltilovessimpcity@simpcityhatesscrapers"


class JPG5Crawler(CheveretoCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/...",
        "Image": "/img/...",
        "Profile": "/<user_name>",
        "Direct links": "",
    }

    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = (
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
    DOMAIN: ClassVar[str] = "jpg5.su"
    FOLDER_DOMAIN: ClassVar[str] = "JPG5"

    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://jpg5.su")

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(1, 5)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = scrape_item.url.with_host("jpg5.su")
        return await self._fetch_chevereto_defaults(scrape_item)

    async def video(self, scrape_item: ScrapeItem) -> None:
        raise ValueError

    def parse_url(
        self, link_str: str, relative_to: AbsoluteHttpURL | None = None, *, trim: bool = True
    ) -> AbsoluteHttpURL:
        if not link_str.startswith("https") and not link_str.startswith("/"):
            link_str = decrypt_xor(link_str, DECRYPTION_KEY)
        return super().parse_url(link_str, relative_to, trim=trim)

    async def handle_direct_link(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None) -> None:
        """Handles a direct link."""
        link = url or scrape_item.url
        link = self.parse_url(re.sub(JPG5_REPLACE_HOST_REGEX, r"host.church/", str(link)))
        await super().handle_direct_link(scrape_item, link)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def decrypt_xor(encrypted_str: str, key: bytes) -> str:
    div = len(key)
    encrypted = bytes.fromhex(binascii.a2b_base64(encrypted_str).decode())
    return bytes([encrypted[i] ^ key[i % div] for i in range(len(encrypted))]).decode()
