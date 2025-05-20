from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.kemono import KemonoCrawler
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class NekohouseCrawler(KemonoCrawler):
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {
        "Model": "/<service>/user/",
        "Individual Post": "/user/post/",
        "Direct links": "",
    }
    primary_base_domain = AbsoluteHttpURL("https://nekohouse.su")
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date} - {title}"
    DOMAIN = "nekohouse"
    FOLDER_DOMAIN = "Nekohouse"
    SERVICES = "fanbox", "fantia", "fantia_products", "subscribestar", "twitter"
    API_ENTRYPOINT = None  # type: ignore

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
