from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


API_ENTRYPOINT = URL("https://api.files.vc/api")


class FilesVcCrawler(Crawler):
    primary_base_domain = URL("https://files.vc")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "files.vc", "FilesVC")
        self.request_limiter = AsyncLimiter(1, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if scrape_item.url.path == "/d/dl" and scrape_item.url.query.get("hash"):
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""

        if await self.check_complete_from_referer(scrape_item):
            return

        hash = scrape_item.url.query["hash"]
        api_url = API_ENTRYPOINT.joinpath("info").with_query(hash=hash)

        async with self.request_limiter:
            json_resp: dict[str, Any] = await self.client.get_json(self.domain, api_url)

        filename, ext = self.get_filename_and_ext(json_resp["filename"], assume_ext=".zip")
        scrape_item.possible_datetime = self.parse_date(json_resp["upload_time"])
        link = self.parse_url(json_resp["file_url"])
        await self.handle_file(link, scrape_item, filename, ext)
