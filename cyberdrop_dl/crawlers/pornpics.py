from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

COLLECTION_PARTS = "search", "channel", "pornstar", "tag", "category"
IMAGE_SELECTOR = "div#main a.rel-link"
BASE_HOST: str = "pornpics.com"

PRIMARY_URL = AbsoluteHttpURL("https://pornpics.com")


class PornPicsCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Categories": "/categories/....",
        "Channels": "/channels/...",
        "Gallery": "/galleries/...",
        "Pornstars": "/pornstars/...",
        "Search": "/?q=<query>",
        "Tags": "/tags/...",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "pornpics"
    FOLDER_DOMAIN: ClassVar[str] = "PornPics"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        parts_limit = 2 if scrape_item.url.name else 3
        multi_part = len(scrape_item.url.parts) > parts_limit
        collection_part = next((p.removesuffix("s") for p in COLLECTION_PARTS if p in scrape_item.url.parts), None)
        if is_cdn(scrape_item.url):
            return await self.image(scrape_item)
        if "galleries" in scrape_item.url.parts and multi_part:
            return await self.gallery(scrape_item)
        if multi_part and collection_part:
            return await self.collection(scrape_item, collection_part)
        if len(scrape_item.url.parts) == parts_limit:
            return await self.collection(scrape_item, "category")
        if scrape_item.url.query.get("q"):
            return await self.collection(scrape_item, "search")
        raise ValueError

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: str) -> None:
        assert collection_type in COLLECTION_PARTS

        def update_scrape_item(soup: BeautifulSoup) -> None:
            selector = "h2" if collection_type == "channel" else "h1"
            title = css.select_one_get_text(soup, selector).removesuffix(" Nude Pics").removesuffix(" Porn Pics")
            title = self.create_title(f"{title} [{collection_type}]")
            scrape_item.setup_as_profile(title)

        async for soup, items in self._web_pager(scrape_item):
            if soup:
                update_scrape_item(soup)

            for link in items:
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        gallery_base = scrape_item.url.name or scrape_item.url.parent.name
        gallery_id = gallery_base.rsplit("-", 1)[-1]
        results = await self.get_album_results(gallery_id)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        scrape_item.url = PRIMARY_URL / "galleries" / gallery_id  # canonical URL
        title = css.select_one_get_text(soup, "h1")
        title = self.create_title(title, gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)

        for _, new_scrape_item in self.iter_children(scrape_item, soup, IMAGE_SELECTOR):
            if not self.check_album_results(new_scrape_item.url, results):
                filename, ext = self.get_filename_and_ext(new_scrape_item.url.name)
                await self.handle_file(new_scrape_item.url, new_scrape_item, filename, ext)

    async def image(self, scrape_item: ScrapeItem) -> None:
        scrape_item.album_id = scrape_item.url.parts[-2]
        await self.direct_file(scrape_item)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~``

    async def _web_pager(
        self, scrape_item: ScrapeItem
    ) -> AsyncGenerator[tuple[BeautifulSoup | None, tuple[AbsoluteHttpURL, ...]]]:
        """Generator of website pages."""
        limit = 20
        page_url = scrape_item.url.without_query_params("limit", "offset")
        offset = int(scrape_item.url.query.get("offset") or 0)

        async def get_items(current_page: AbsoluteHttpURL) -> tuple[BeautifulSoup | None, tuple[AbsoluteHttpURL, ...]]:
            offset = current_page.query.get("offset")
            if not offset:  # offset == 0 does not return JSON
                async with self.request_limiter:
                    soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, current_page)
                items = soup.select(IMAGE_SELECTOR)
                return soup, tuple(self.parse_url(css.get_attr(image, "href")) for image in items)

            async with self.request_limiter:
                # The response is JSON but the "content-type" is wrong so we have to request it as text
                json_resp = await self.client.get_text(self.DOMAIN, current_page)
                json_resp = json.loads(json_resp)
            return None, tuple(self.parse_url(g["g_url"]) for g in json_resp)

        while True:
            soup, items = await get_items(page_url)
            yield soup, items
            if len(items) < limit:
                break
            offset += limit
            page_url = page_url.update_query(offset=offset, limit=limit)


def is_cdn(url: AbsoluteHttpURL) -> bool:
    url_host: str = url.host.removeprefix("www.")
    return len(url_host.split(".")) > len(BASE_HOST.split("."))
