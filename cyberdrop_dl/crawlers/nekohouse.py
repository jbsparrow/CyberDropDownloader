from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .kemono import KemonoBaseCrawler


class NekohouseCrawler(KemonoBaseCrawler):
    SUPPORTED_PATHS: ClassVar[dict[str, str]] = {
        "Model": "/<service>/user/<user_id>",
        "Individual Post": "/<service>/user/<user_id>/post/<post_id>",
        "Direct links": "/(data|thumbnails)/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://nekohouse.su")
    DOMAIN: ClassVar[str] = "nekohouse"
    SERVICES = "fanbox", "fantia", "fantia_products", "subscribestar", "twitter"

    async def async_startup(self) -> None:
        await super().async_startup()

        # Only this API endpoint is available
        await self._get_usernames(self.PRIMARY_URL / "api/creators")
