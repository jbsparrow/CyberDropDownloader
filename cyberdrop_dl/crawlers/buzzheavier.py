from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_from_headers

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class BuzzHeavierCrawler(Crawler):
    primary_base_domain = URL("https://buzzheavier.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "buzzheavier.com", "BuzzHeavier")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        return await self.file(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""

        if await self.check_complete_from_referer(scrape_item):
            return

        url = scrape_item.url / "download"
        headers = {"HX-Current-URL": str(scrape_item.url), "HX-Request": "true"}
        async with self.request_limiter:
            headers = await self.client.get_head(self.domain, url, headers=headers)
            redirect = headers["hx-redirect"]
            filename = get_filename_from_headers(headers)

        assert filename
        link = self.parse_url(redirect)
        filename, ext = self.get_filename_and_ext(filename, assume_ext=".zip")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=link)
