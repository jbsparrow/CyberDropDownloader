from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._chevereto import CheveretoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import SupportedDomains
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_OLD_DOMAINS = (
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
    "jpg5.su",
    "host.church",
)

_REPLACE_OLD_HOST_REGEX = re.compile("|".join(_OLD_DOMAINS))


class JPG5Crawler(CheveretoCrawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = (*_OLD_DOMAINS, "jpg6.su")
    DOMAIN: ClassVar[str] = "jpg5.su"
    FOLDER_DOMAIN: ClassVar[str] = "JPG5"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://jpg6.su")
    CHEVERETO_SUPPORTS_VIDEO: ClassVar[bool] = False

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(1, 1)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = _fix_host(scrape_item.url)
        return await super().fetch(scrape_item)

    async def handle_direct_link(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None) -> None:
        link = url or scrape_item.url
        link = _fix_host(link)
        await super().handle_direct_link(scrape_item, link)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def _fix_host(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    new_host = re.sub(_REPLACE_OLD_HOST_REGEX, r"jpg5.su", url.host)
    if new_host.removeprefix("www.") == "jpg5.su":
        # replace only if it is matches the second level domain exactly
        # old jpg5 subdomains are still valid. ex: simp4.jpg5.su
        return url.with_host("jpg6.su")
    return url.with_host(new_host)


def fix_db_referer(referer: str) -> str:
    url = AbsoluteHttpURL(referer)
    return str(_fix_host(url))
