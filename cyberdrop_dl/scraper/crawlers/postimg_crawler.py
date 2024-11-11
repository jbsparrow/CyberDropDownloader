from __future__ import annotations

import contextlib
import itertools
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class PostImgCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "postimg", "PostImg")
        self.api_address = URL("https://postimg.cc/json")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "i.postimg.cc" in scrape_item.url.host:
            filename, ext = get_filename_and_ext(scrape_item.url.name)
            await self.handle_file(scrape_item.url, scrape_item, filename, ext)
        elif "gallery" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.image(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        data = {"action": "list", "album": scrape_item.url.raw_name, "page": 0}
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]
        for i in itertools.count(1):
            data["page"] = i
            async with self.request_limiter:
                JSON_Resp = await self.client.post_data(self.domain, self.api_address, data=data, origin=scrape_item)

            scrape_item.part_of_album = True
            scrape_item.album_id = scrape_item.url.parts[2]
            title = self.create_title(scrape_item.url.raw_name, scrape_item.album_id, None)

            for image in JSON_Resp["images"]:
                link = URL(image[4])
                filename, ext = image[2], image[3]
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    True,
                    add_parent=scrape_item.url,
                )
                await self.handle_file(link, new_scrape_item, filename, ext)
                scrape_item.children += 1
                if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                    raise MaxChildrenError(origin=scrape_item)

            if not JSON_Resp["has_page_next"]:
                break

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link = URL(soup.select_one("a[id=download]").get("href").replace("?dl=1", ""))
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
