from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._kemono_base import KemonoBaseCrawler

PRIMARY_URL = AbsoluteHttpURL("https://kemono.su")


class KemonoCrawler(KemonoBaseCrawler):
    SUPPORTED_PATHS: ClassVar = KemonoBaseCrawler.SUPPORTED_PATHS | {
        "Discord Server": "/discord/<server_id>",
        "Discord Server Channel": "/discord/server/...#...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    API_ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://kemono.su/api/v1")
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
