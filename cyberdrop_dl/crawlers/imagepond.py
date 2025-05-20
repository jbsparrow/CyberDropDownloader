from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.types import AbsoluteHttpURL, SupportedPaths

PRIMARY_URL = AbsoluteHttpURL("https://imagepond.net")


class ImagePondCrawler(CheveretoCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/...",
        "Image": "/img/...",
        "Profiles": "/...",
        "Video": "/video/..",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "imagepond.net"
    FOLDER_DOMAIN: ClassVar[str] = "ImagePond"
