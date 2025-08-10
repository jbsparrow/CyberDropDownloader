from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import MediaItem, ScrapeItem
    from cyberdrop_dl.utils import m3u8


CDN_HOST = "pbs.twimg.com"
PRIMARY_URL = AbsoluteHttpURL("https://twimg.com/")


class TwimgCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Photo": "/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "twimg"
    FOLDER_DOMAIN: ClassVar[str] = "TwitterImages"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "video" in scrape_item.url.host:
            return await self.direct_file(scrape_item)
        await self.photo(scrape_item)

    async def photo(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None) -> None:
        # https://developer.x.com/en/docs/x-api/v1/data-dictionary/object-model/entities#photo_format
        link = url or scrape_item.url
        if "emoji" in link.parts:
            return

        # name could be "orig", "4096x4096", "large", "medium", or "small"
        # `orig`` is original quality but it's not always available, same as "4096x4096"
        # "large", "medium", or "small" are always avaliable

        link = link.with_host(CDN_HOST).with_query(format="png", name="orig")
        filename = Path(link.name).with_suffix(".png").as_posix()
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext)

    async def handle_media_item(self, media_item: MediaItem, m3u8: m3u8.RenditionGroup | None = None) -> None:
        formats = "png", "jpg"
        names = "orig", "4096x4096", "large"
        media_item.fallbacks = []

        for f in formats:
            for name in names:
                url = media_item.url.update_query(format=f, name=name)
                if url != media_item.url:
                    media_item.fallbacks.append(url)

        return await super().handle_media_item(media_item, m3u8)
