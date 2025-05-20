from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping

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
    DOMAIN = "imagepond.net"
    FOLDER_DOMAIN = "ImagePond"
