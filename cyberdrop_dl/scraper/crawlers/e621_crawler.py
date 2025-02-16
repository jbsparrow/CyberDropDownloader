from __future__ import annotations

import calendar
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from dateutil import parser
from yarl import URL

from cyberdrop_dl import __version__
from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager


class E621Crawler(Crawler):
    primary_base_domain = URL("https://e621.net")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "e621.net", "E621")
        self.custom_headers = {"User-Agent": f"CyberDrop-DL/{__version__} (by B05FDD249DF29ED3)"}
        self.request_limiter = AsyncLimiter(2, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the URL."""

        if "tags" in scrape_item.url.query_string:
            await self.tag(scrape_item)
        elif scrape_item.url.path.startswith("/posts/"):
            await self.file(scrape_item)
        elif scrape_item.url.path.startswith("/pools/"):
            await self.pool(scrape_item)
        else:
            raise ValueError("Invalid e621 URL format")

    async def paginator(self, scrape_item: ScrapeItem) -> AsyncGenerator[dict]:
        """Generator for album pages."""
        page = int(scrape_item.url.query.get("page", 1))
        while True:
            async with self.request_limiter:
                params = {"tags": scrape_item.url.query["tags"], "page": page}
                response = await self.client.get_json(
                    self.domain,
                    self.primary_base_domain / "posts.json",
                    params=params,
                    origin=scrape_item,
                    headers_inc=self.custom_headers,
                )
            posts = response.get("posts", [])
            yield posts
            if posts:
                page += 1
                continue
            break

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Fetches posts from e621 based on tags."""
        tags = scrape_item.url.query["tags"]
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        title = self.create_title(tags.replace("+", " "))
        scrape_item.part_of_album = True

        async for response in self.paginator(scrape_item):
            for post in response:
                file_url = post.get("file", {}).get("url")
                if not file_url:
                    continue

                creation_date = post.get("created_at")
                timestamp = self.parse_datetime(creation_date)

                link = self.parse_url(file_url)
                new_scrape_item = self.create_scrape_item(
                    scrape_item, link, title, True, add_parent=scrape_item.url, possible_datetime=timestamp
                )
                scrape_item.add_children()
                filename, ext = get_filename_and_ext(link.name)
                await self.handle_file(link, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def pool(self, scrape_item: ScrapeItem) -> None:
        """Fetches posts from an e621 pool."""
        async with self.request_limiter:
            pool_id = scrape_item.url.path.rsplit("/", 1)[-1]
            response = await self.client.get_json(
                self.domain,
                self.primary_base_domain / f"pools/{pool_id}.json",
                origin=scrape_item,
                headers_inc=self.custom_headers,
            )

        posts = response.get("post_ids", [])
        title = response.get("name", "Unknown Pool").replace("_", " ")
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.part_of_album = True

        for post_id in posts:
            new_scrape_item = self.create_scrape_item(
                scrape_item, self.primary_base_domain / f"posts/{post_id}", title, True, add_parent=scrape_item.url
            )
            await self.file(new_scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Fetches a single post by extracting the ID from the URL."""
        async with self.request_limiter:
            post_id = scrape_item.url.path.rsplit("/", 1)[-1]
            response = await self.client.get_json(
                self.domain,
                self.primary_base_domain / f"posts/{post_id}.json",
                origin=scrape_item,
                headers_inc=self.custom_headers,
            )

        post = response.get("post", {})
        file_url = post.get("file", {}).get("url")
        if not file_url:
            raise ScrapeError(422, origin=scrape_item)

        link = self.parse_url(file_url)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = parser.isoparse(date)
        return calendar.timegm(parsed_date.utctimetuple())
