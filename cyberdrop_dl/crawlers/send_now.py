from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from curl_cffi.requests.models import Response as CurlResponse

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class SendNowCrawler(Crawler):
    primary_base_domain = URL("https://send.now/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "send.now", "SendNow")
        self.got_cookies = False

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        await self.file(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        file_id = scrape_item.url.name
        data = {"op": "download2", "id": file_id, "rand": "", "referer": "", "method_free": "", "method_premium": ""}
        params = {"allow_redirects": False, "stream": True}

        async with self.request_limiter:
            response: CurlResponse = await self.client.post_data_cffi(
                self.domain, scrape_item.url, data=data, request_params=params
            )

        debrid_link = self.parse_url(response.headers.get("location"))
        filename, ext = self.get_filename_and_ext(debrid_link.name, assume_ext=".zip")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=debrid_link)

    async def get_cookies(self, scrape_item) -> None:
        async with self.startup_lock:
            if not self.got_cookies:
                async with self.request_limiter:
                    await self.client.get_soup_cffi(self.domain, scrape_item.url)
                cookies = self.manager.client_manager.cookies.filter_cookies(self.primary_base_domain)
                self.got_cookies = bool(cookies)
