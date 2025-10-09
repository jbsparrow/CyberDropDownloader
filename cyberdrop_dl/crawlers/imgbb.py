from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import SupportedDomains, SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


IMAGES_CDN: Final = "i.ibb.co"


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
        username, _, rest = scrape_item.url.host.partition(".imgbb.")
        if username and rest:
            return await self.profile(scrape_item)

        if scrape_item.url.host == IMAGES_CDN:
            return await self.direct_file(scrape_item)

        match scrape_item.url.parts[1:]:
            case ["albums", album_id]:
                return await self.album(scrape_item, album_id)
            case [_]:
                return await self.media(scrape_item)

    @classmethod
    def _match_img(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        match url.parts[1:]:
            case [_]:
                return url

    async def direct_file(
        self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None, assume_ext: str | None = None
    ) -> None:
        link = self._thumbnail_to_src(url or scrape_item.url)
        if scrape_item.url.host == IMAGES_CDN and len(scrape_item.url.parts) > 1:
            image_id = scrape_item.url.parts[1]
            scrape_item.url = self.PRIMARY_URL / image_id
        await super().direct_file(scrape_item, link, assume_ext)
