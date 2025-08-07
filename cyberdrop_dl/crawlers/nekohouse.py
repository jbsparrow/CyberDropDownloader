from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._kemono_base import KemonoBaseCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class NekohouseCrawler(KemonoBaseCrawler):
    SUPPORTED_PATHS: ClassVar[dict[str, str]] = {
        "Model": "/<service>/user/<user>",
        "Individual Post": "/<service>/<user>/post/...",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://nekohouse.su")
    DOMAIN: ClassVar[str] = "nekohouse"
    SERVICES = "fanbox", "fantia", "fantia_products", "subscribestar", "twitter"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "thumbnails" in scrape_item.url.parts:
            return await self.handle_direct_link(scrape_item)
        if "post" in scrape_item.url.parts:
            return await self.post_w_no_api(scrape_item)
        if any(x in scrape_item.url.parts for x in self.SERVICES):
            return await self.profile_w_no_api(scrape_item)
        if any(x in scrape_item.url.parts for x in ("posts", "discord")):
            raise ValueError

        await self.handle_direct_link(scrape_item)
