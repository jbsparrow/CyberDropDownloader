from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._kvs import KernelVideoSharingCrawler, Video
from cyberdrop_dl.crawlers.porntrex import PorntrexCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils import css, open_graph

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.crawlers.crawler import SupportedPaths


PRIMARY_URL = AbsoluteHttpURL("https://www.camwhores.tv")
LAST_PAGE_SELECTOR = "div.pagination-holder li.page"


class CamwhoresTVCrawler(KernelVideoSharingCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Search": "/search/...",
        "Categories": "/categories/...",
        "Tags": "/tags/...",
        "Videos": "/videos/...",
        "Members": "/members/<member_id>",
    }

    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "camwhores.tv"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        # Returns 404 without the trailing slash
        if scrape_item.url.name:
            scrape_item.url = scrape_item.url / ""
        await super().fetch(scrape_item)

    def get_video_info(self, soup: BeautifulSoup) -> Video:
        video = super().get_video_info(soup)
        return video._replace(title=open_graph.title(soup))

    def parse_url(
        self, link_str: str, relative_to: AbsoluteHttpURL | None = None, *, trim: bool = False
    ) -> AbsoluteHttpURL:
        return super().parse_url(link_str, relative_to, trim=False)

    async def picture(self, scrape_item: ScrapeItem) -> None:
        # images are encrypted, similar to the video URLS
        # https://www.camwhores.tv/get_image/93/9da0742b1fb753388286b95c2a66d766/sources/100000/100557/1472879.jpg/
        # TODO: Find out license to decrypt them
        # Almost all albums are private anyways..
        raise NotImplementedError

    async def album(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    async def iter_videos(self, scrape_item: ScrapeItem, video_category: str = "") -> None:
        url = scrape_item.url / video_category if video_category else scrape_item.url
        await super().iter_videos(scrape_item, video_category)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, url)

        last_page = int(css.get_text(soup.select(LAST_PAGE_SELECTOR)[-1]))
        # TODO: Porntrex also uses KVS. Make the KVS crawler handle it by default
        await PorntrexCrawler.proccess_additional_pages(
            self,  # type: ignore[ArgumentType]
            scrape_item,
            last_page,
            block_id="list_videos_common_videos_list",
        )
