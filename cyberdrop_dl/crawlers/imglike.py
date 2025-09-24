from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, copy_signature

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

PRIMARY_URL = AbsoluteHttpURL("https://imglike.com")


class ImgLikeCrawler(CheveretoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "imglike.com"
    FOLDER_DOMAIN: ClassVar[str] = "ImgLike"

    @copy_signature(Crawler.request_soup)
    async def request_soup(self, url: AbsoluteHttpURL, *args, impersonate: bool = False, **kwargs) -> BeautifulSoup:
        impersonate = impersonate or "image" in url.parts
        return await super().request_soup(url, *args, impersonate=impersonate, **kwargs)
