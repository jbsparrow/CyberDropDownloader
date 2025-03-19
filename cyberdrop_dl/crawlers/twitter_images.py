from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class TwimgCrawler(Crawler):
    primary_base_domain = URL("https://twimg.com/")
    cdn_base_domain = URL("https://pbs.twimg.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "twimg", "TwitterImages")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "media" not in scrape_item.url.parts:
            raise ValueError
        await self.photo(scrape_item)

    async def photo(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a photo.

        See: https://developer.x.com/en/docs/x-api/v1/data-dictionary/object-model/entities#photo_format
        """
        scrape_item.url = scrape_item.url.with_host(self.cdn_base_domain.host).with_query(None)
        link = scrape_item.url.with_query(format="jpg", name="large")
        filename, ext = get_filename_and_ext(f"{link.name}.jpg")
        await self.handle_file(link, scrape_item, filename, ext)
