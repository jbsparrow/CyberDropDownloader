from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


CDN_HOST = "pbs.twimg.com"
PRIMARY_BASE_DOMAIN = URL("https://twimg.com/")


class TwimgCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "twimg", "TwitterImages")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "video" in scrape_item.url.host:
            await self.direct_file(scrape_item)
        else:
            await self.photo(scrape_item)

    async def photo(self, scrape_item: ScrapeItem, url: URL | None = None) -> None:
        """Scrapes a photo.

        See: https://developer.x.com/en/docs/x-api/v1/data-dictionary/object-model/entities#photo_format
        """
        link = url or scrape_item.url
        link = link.with_host(CDN_HOST).with_query(format="jpg", name="large")
        filename = str(Path(link.name).with_suffix(".jpg"))
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext)
