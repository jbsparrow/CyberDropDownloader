from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_PRIMARY_URL = AbsoluteHttpURL("https://wetransfer.com/")
_API_ENTRYPOINT = _PRIMARY_URL / "api/v4/transfers"


class WeTransferCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Public link": "wetransfer.com/downloads/<file_id>/<security_hash>",
        "Share Link": "wetransfer.com/downloads/<file_id>/<recipient_id>/<security_hash>",
        "Short Link": "we.tl/<short_file_id>",
        "Direct links": "download.wetransfer.com/...",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "wetransfer.com", "we.tl"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "wetransfer"
    FOLDER_DOMAIN: ClassVar[str] = "WeTransfer"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_] if scrape_item.url.host == "we.tl":
                return await self.follow_redirect(scrape_item)
            case ["downloads", file_id, security_hash]:
                return await self.file(scrape_item, file_id, security_hash)
            case ["downloads", file_id, recipient_id, security_hash]:
                return await self.file(scrape_item, file_id, security_hash, recipient_id)
            case [*_] if "download." in scrape_item.url.host:
                return await self.direct_file(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def _json_response_check(cls, json_resp: dict[str, Any]) -> None:
        if json_resp.get("direct_link"):
            return

        msg: str = json_resp.get("message") or ""
        if "No download access to this Transfer" in msg:
            code = 401
        elif "Couldn't find Transfer" in msg:
            code = 410
        else:
            code = 422
        raise ScrapeError(code, msg)

    @error_handling_wrapper
    async def file(
        self, scrape_item: ScrapeItem, file_id: str, security_hash: str, recipient_id: str | None = None
    ) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        payload = {"intent": "entire_transfer", "security_hash": security_hash}
        if recipient_id:
            payload["recipient_id"] = recipient_id

        api_url = _API_ENTRYPOINT / file_id / "download"
        resp: dict[str, str] = await self.request_json(api_url, method="POST", json=payload)
        link = self.parse_url(resp["direct_link"])
        await self.direct_file(scrape_item, link)
