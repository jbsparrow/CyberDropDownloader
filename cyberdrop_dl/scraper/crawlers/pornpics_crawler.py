from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class PornPicCrawler(Crawler):
    primary_base_domain = URL("https://pornpics.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pornpics", "PornPics")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        ...

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        ...

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image page."""
        ...
