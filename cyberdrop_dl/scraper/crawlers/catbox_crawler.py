from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


CDN_HOSTS = "litter.catbox.moe", "files.catbox.moe"


class CatboxCrawler(Crawler):
    primary_base_domain = URL("https://catbox.moe")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "catbox.moe", "Catbox")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p == scrape_item.url.host for p in CDN_HOSTS):
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        filename, ext = self.get_filename_and_ext(scrape_item.url.name, assume_ext=".zip")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)
