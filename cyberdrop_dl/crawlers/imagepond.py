from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

PRIMARY_URL = AbsoluteHttpURL("https://imagepond.net")


class ImagePondCrawler(CheveretoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "imagepond.net"
    FOLDER_DOMAIN: ClassVar[str] = "ImagePond"
