from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem

from ._kemono_base import KemonoBaseCrawler


class KemonoCrawler(KemonoBaseCrawler):
    SUPPORTED_PATHS: ClassVar = KemonoBaseCrawler.SUPPORTED_PATHS | {
        "Discord Server": "/discord/<server_id>",
        "Discord Server Channel": "/discord/server/...#...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://kemono.cr")
    API_ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://kemono.cr/api/v1")
    DOMAIN: ClassVar[str] = "kemono"
    SERVICES: ClassVar[tuple[str, ...]] = (
        "afdian",
        "boosty",
        "dlsite",
        "fanbox",
        "fantia",
        "gumroad",
        "patreon",
        "subscribestar",
    )
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = "kemono.party", "kemono.su"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "discord" in scrape_item.url.parts:
            return await self.discord(scrape_item)
        return await super().fetch(scrape_item)
