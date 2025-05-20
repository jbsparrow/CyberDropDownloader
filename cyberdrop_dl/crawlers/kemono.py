from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.types import AbsoluteHttpURL

from ._kemono_base import KemonoBaseCrawler

PRIMARY_URL = AbsoluteHttpURL("https://kemono.su")


class KemonoCrawler(KemonoBaseCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "kemono"
    API_ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://kemono.su/api/v1")
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
