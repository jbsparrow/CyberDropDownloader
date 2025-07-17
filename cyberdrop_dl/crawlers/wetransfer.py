from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://wetransfer.com/")
API_ENTRYPOINT = AbsoluteHttpURL("https://wetransfer.com/api/v4/transfers")


class WeTransferCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Public link": "wetransfer.com/<file_id>/<security_hash>",
        "Share Link": "wetransfer.com/<file_id>/<recipient_id>/<security_hash>",
        "Short Link": "we.tl/<id>",
        "Direct links": "download.wetransfer.com/...",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "wetransfer.com", "we.tl"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "wetransfer"
    FOLDER_DOMAIN: ClassVar[str] = "WeTransfer"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "download." in scrape_item.url.host:
            # We can download but db entry will not have a canonical URL
            return await self.direct_link(scrape_item, scrape_item.url)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.host == "we.tl":
            scrape_item.url = await self.get_final_url(scrape_item)

        file_info = get_file_info(scrape_item.url)
        if await self.check_complete_from_referer(file_info.download_url):
            return

        async with self.request_limiter:
            json_resp: dict = await self.client.post_data(self.DOMAIN, file_info.download_url, json=file_info.json)

        link_str: str | None = json_resp.get("direct_link")
        if not link_str:
            code, msg = parse_error(json_resp)
            raise ScrapeError(code, message=msg)

        link = self.parse_url(link_str)
        await self.direct_link(scrape_item, link)

    @error_handling_wrapper
    async def direct_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL) -> None:
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    async def get_final_url(self, scrape_item: ScrapeItem) -> AbsoluteHttpURL:
        async with self.request_limiter:
            headers = await self.client.get_head(self.DOMAIN, scrape_item.url)

        return self.parse_url(headers["location"])


@dataclass(frozen=True, order=True)
class FileInfo:
    id: str
    security_hash: str
    recipient_id: str | None = None

    @property
    def json(self) -> str:
        details = {"intent": "entire_transfer", "security_hash": self.security_hash}
        if self.recipient_id:
            details["recipient_id"] = self.recipient_id
        return json.dumps(details)

    @property
    def download_url(self) -> AbsoluteHttpURL:
        return API_ENTRYPOINT / self.id / "download"


def get_file_info(url: AbsoluteHttpURL) -> FileInfo:
    parts = [p for p in url.parts if p not in ("/", "downloads")]
    assert len(parts) >= 2
    if len(parts) >= 3:
        return FileInfo(id=parts[0], recipient_id=parts[0], security_hash=parts[2])
    return FileInfo(id=parts[0], security_hash=parts[1])


def parse_error(json_resp: dict) -> tuple[int, str | None]:
    msg = json_resp.get("message") or ""
    code = get_error_code(msg)
    return code, msg or None


def get_error_code(msg: str) -> int:
    if msg == "No download access to this Transfer":
        return 401
    if "Couldn't find Transfer" in msg:
        return 410
    return 422
