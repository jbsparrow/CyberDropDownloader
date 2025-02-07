from __future__ import annotations

import json
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class PornPicsCrawler(Crawler):
    primary_base_domain = URL("https://pornpics.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pornpics", "PornPics")
        self.image_selector = "div#main a.rel-link"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        parts_limit = 2 if scrape_item.url.name else 3
        multi_part = len(scrape_item.url.parts) > parts_limit
        if self.is_cdn(scrape_item.url):
            await self.image(scrape_item)
        elif "galleries" in scrape_item.url.parts and multi_part:
            await self.gallery(scrape_item)
        elif "channels" in scrape_item.url.parts and multi_part:
            await self.collection(scrape_item, "channel")
        elif "pornstars" in scrape_item.url.parts and multi_part:
            await self.collection(scrape_item, "pornstar")
        elif "tags" in scrape_item.url.parts and multi_part:
            await self.collection(scrape_item, "tag")
        elif len(scrape_item.url.parts) == parts_limit:
            await self.collection(scrape_item, "category")
        elif scrape_item.url.query.get("q"):
            await self.collection(scrape_item, "search")
        else:
            raise ValueError

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, type: str) -> None:
        """Scrapes a collection."""
        assert type in ("search", "channel", "pornstar", "tag", "category")

        def update_scrape_item(soup: BeautifulSoup) -> None:
            selector = "h2" if type == "channel" else "h1"
            title = soup.select_one(selector).text.removesuffix(" Nude Pics").removesuffix(" Porn Pics")
            title = self.create_title(f"{title} [{type}]")
            scrape_item.add_to_parent_title(title)
            scrape_item.part_of_album = True
            scrape_item.set_type(FILE_HOST_PROFILE, self.manager)

        async for soup, items in self._web_pager(scrape_item):
            if soup:
                update_scrape_item(soup)
            for link in items:
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a gallery."""
        gallery_base = scrape_item.url.name or scrape_item.url.parent.name
        gallery_id = gallery_base.rsplit("-", 1)[-1]
        results = await self.get_album_results(gallery_id)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        canonical_url = self.primary_base_domain / "galleries" / gallery_id
        scrape_item.url = canonical_url
        title = soup.select_one("h1").text
        title = self.create_title(title, gallery_id)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True
        scrape_item.album_id = gallery_id
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        images = soup.select(self.image_selector)

        for image in images:
            link_str: str = image.get("href")
            link = self.parse_url(link_str)
            if not self.check_album_results(link, results):
                filename, ext = get_filename_and_ext(link.name)
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.add_children()

    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        link = scrape_item.url
        gallery_id = link.parts[-2]
        filename, ext = get_filename_and_ext(link.name)
        scrape_item.album_id = gallery_id
        await self.handle_file(link, scrape_item, filename, ext)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~``

    async def _web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[tuple[BeautifulSoup | None, list[URL]]]:
        """Generator of website pages."""
        limit = 20
        page_url = scrape_item.url.without_query_params("limit", "offset")
        offset = int(scrape_item.url.query.get("offset") or 0)
        while True:
            soup, items = await self._get_items(scrape_item, page_url)
            yield (soup, items)
            if len(items) < limit:
                break
            offset += limit
            page_url = page_url.update_query(offset=offset, limit=limit)

    async def _get_items(self, scrape_item: ScrapeItem, page_url: URL) -> tuple[BeautifulSoup | None, list[URL]]:
        offset = page_url.query.get("offset")
        if not offset:  # offset = 0 does not return JSON
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            items = soup.select(self.image_selector)
            return soup, [self.parse_url(image.get("href")) for image in items]

        async with self.request_limiter:
            # The response is JSON but the "content-type" is wrong so we have to request it as text
            json_resp = await self.client.get_text(self.domain, page_url, origin=scrape_item)
            json_resp = json.loads(json_resp)
        return None, [self.parse_url(g["g_url"]) for g in json_resp]

    def is_cdn(self, url: URL) -> bool:
        assert url.host, f"{url} has no host"
        base_host: str = self.primary_base_domain.host.removeprefix("www.")
        url_host: str = url.host.removeprefix("www.")
        return len(url_host.split(".")) > len(base_host.split("."))
