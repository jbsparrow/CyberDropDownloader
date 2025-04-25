from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl import __version__
from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


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
        if scrape_item.url.query.get("tags"):
            return await self.tag(scrape_item)
        if "posts" in scrape_item.url.parts:
            return await self.file(scrape_item)
        if "pools" in scrape_item.url.parts:
            return await self.pool(scrape_item)
        raise ValueError

    async def paginator(self, scrape_item: ScrapeItem) -> AsyncGenerator[list[dict[str, Any]]]:
        """Generator for album pages."""
        initial_page = int(scrape_item.url.query.get("page", 1))
        url = self.primary_base_domain / "posts.json"
        for page in itertools.count(initial_page):
            url = url.with_query(tags=scrape_item.url.query["tags"], page=page)
            async with self.request_limiter:
                json_resp: dict = await self.client.get_json(self.domain, url, headers_inc=self.custom_headers)

            posts: list[dict] = json_resp.get("posts", [])
            if not posts:
                break
            yield posts

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Fetches posts from e621 based on tags."""
        tags = scrape_item.url.query["tags"]
        title = self.create_title(tags.replace("+", " "))
        scrape_item.setup_as_album(title)

        async for posts in self.paginator(scrape_item):
            for post in posts:
                try:
                    file_url = post["file"]["url"]
                except KeyError:
                    continue
                timestamp = self.parse_date(post["created_at"])
                link = self.parse_url(file_url)
                new_scrape_item = scrape_item.create_child(link, possible_datetime=timestamp)
                filename, ext = self.get_filename_and_ext(link.name)
                await self.handle_file(link, new_scrape_item, filename, ext)
                scrape_item.add_children()

    @error_handling_wrapper
    async def pool(self, scrape_item: ScrapeItem) -> None:
        """Fetches posts from an e621 pool."""
        pool_id = scrape_item.url.name
        url = self.primary_base_domain / f"pools/{pool_id}.json"
        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.domain, url, headers_inc=self.custom_headers)

        posts = json_resp.get("post_ids", [])
        title: str = json_resp.get("name", "Unknown Pool").replace("_", " ")
        scrape_item.setup_as_album(title)

        for post_id in posts:
            url = self.primary_base_domain / f"posts/{post_id}"
            new_scrape_item = scrape_item.create_child(url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Fetches a single post by extracting the ID from the URL."""
        post_id = scrape_item.url.name
        url = self.primary_base_domain / f"posts/{post_id}.json"
        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.domain, url, headers_inc=self.custom_headers)

        try:
            file_url = json_resp["post"]["file"]["url"]
        except KeyError:
            raise ScrapeError(422) from None

        link = self.parse_url(file_url)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
