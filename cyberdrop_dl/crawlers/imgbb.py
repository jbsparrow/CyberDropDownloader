from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import SupportedDomains, SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class ImgBBCrawler(CheveretoCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/album/<album_id>",
        "Image": "/<image_id>",
        "Profile": "<user_name>.imgbb.co/",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "ibb.co", "imgbb.co"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://ibb.co")
    DOMAIN: ClassVar[str] = "imgbb"
    FOLDER_DOMAIN: ClassVar[str] = "ImgBB"
    SKIP_PRE_CHECK: ClassVar[bool] = True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = scrape_item.url.with_host(self.PRIMARY_URL.host)
        username, _, rest = scrape_item.url.host.partition(".imgbb.")
        if username and rest:
            return await self.profile(scrape_item)

        match scrape_item.url.parts[1:]:
            case ["albums", album_id]:
                return await self.album(scrape_item, album_id)
            case [_]:
                return await self.media(scrape_item)

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        if url.host == "i.ibb.co" and len(url.parts) > 1:
            image_id = url.parts[1]
            return cls.PRIMARY_URL / image_id
        return url
