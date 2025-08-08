from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._kemono_base import KemonoBaseCrawler


class KemonoCrawler(KemonoBaseCrawler):
    SUPPORTED_PATHS: ClassVar = KemonoBaseCrawler.SUPPORTED_PATHS | {
        "Discord Server": "/discord/<server_id>",
        "Discord Server Channel": "/discord/server/<server_id>/<channel_id>#...",
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
