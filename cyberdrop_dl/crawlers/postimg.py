from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://postimages.org/")
DOWNLOAD_BUTTON_SELECTOR = "a[id=download]"
API_ENTRYPOINT = AbsoluteHttpURL("https://postimg.cc/json")


class PostImgCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/gallery/...",
        "Image": "/...",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "postimg"
    FOLDER_DOMAIN: ClassVar[str] = "PostImg"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "i.postimg.cc" in scrape_item.url.host:
            return await self.direct_file(scrape_item)
        if "gallery" in scrape_item.url.parts:
            return await self.album(scrape_item)
        await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        data = {"action": "list", "album": scrape_item.url.raw_name, "page": 0}
        title: str = ""
        for page in itertools.count(1):
            data["page"] = page
            async with self.request_limiter:
                json_resp = await self.client.post_data(self.DOMAIN, API_ENTRYPOINT, data=data)

            if not title:
                album_id = scrape_item.url.parts[2]
                title = self.create_title(scrape_item.url.name, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)

            for image in json_resp["images"]:
                link = self.parse_url(image[4])
                filename, ext = self.get_filename_and_ext(image[2])
                new_scrape_item = scrape_item.create_child(link)
                await self.handle_file(link, new_scrape_item, filename, ext)
                scrape_item.add_children()

            if not json_resp["has_page_next"]:
                break

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str: str = css.select_one_get_attr(soup, DOWNLOAD_BUTTON_SELECTOR, "href")
        link = self.parse_url(link_str).with_query(None)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
