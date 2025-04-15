from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from ._chevereto import CheveretoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

PRIMARY_BASE_DOMAIN = URL("https://jpg5.su")
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

    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        raise ValueError
