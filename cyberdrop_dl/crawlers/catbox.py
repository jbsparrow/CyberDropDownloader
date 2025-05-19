from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


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
            return await self.direct_file(scrape_item, assume_ext=".zip")
        raise ValueError
