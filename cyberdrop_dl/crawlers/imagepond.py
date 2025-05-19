from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

PRIMARY_BASE_DOMAIN = AbsoluteHttpURL("https://imagepond.net")


class ImagePondCrawler(CheveretoCrawler):
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {
        "Album": "/a/...",
        "Image": "/img/...",
        "Profiles": "/...",
        "Video": "/video/..",
        "Direct links": "",
    }
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imagepond.net", "ImagePond")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
