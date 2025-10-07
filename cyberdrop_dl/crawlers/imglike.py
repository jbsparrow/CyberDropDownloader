from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

PRIMARY_URL = AbsoluteHttpURL("https://imglike.com")


class ImgLikeCrawler(CheveretoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "imglike.com"
    FOLDER_DOMAIN: ClassVar[str] = "ImgLike"
