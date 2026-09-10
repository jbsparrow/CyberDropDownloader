from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class SendNowCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Direct links": ""}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://send.now/")
    DOMAIN: ClassVar[str] = "send.now"
    FOLDER_DOMAIN: ClassVar[str] = "SendNow"
    got_cookies: bool = False

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        await self.file(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        file_id = scrape_item.url.name

        async with self.request(
            scrape_item.url,
            method="POST",
            impersonate=True,
            data={
                "op": "download2",
                "id": file_id,
                "rand": "",
                "referer": "",
                "method_free": "",
                "method_premium": "",
            },
        ) as resp:
            debrid_link = resp.location

        assert debrid_link
        filename, ext = self.get_filename_and_ext(debrid_link.name, assume_ext=".zip")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=debrid_link)

    async def _get_cookies(self, scrape_item: ScrapeItem) -> None:
        if self.got_cookies:
            return
        async with self._startup_lock:
            if self.got_cookies:
                return

            async with self.request(scrape_item.url, impersonate=True):
                pass
            cookies = self.client.cookies.filter_cookies(self.PRIMARY_URL)
            self.got_cookies = bool(cookies)
