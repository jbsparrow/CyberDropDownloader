from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl import __version__
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://e621.net")


class E621Crawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Post": "/posts/...",
        "Tags": "/posts?tags=...",
        "Pools": "/pools/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "e621.net"
    FOLDER_DOMAIN: ClassVar[str] = "E621"
    _RATE_LIMIT = 2, 1

    def __post_init__(self) -> None:
        self.headers = {"User-Agent": f"CyberDrop-DL/{__version__} (by B05FDD249DF29ED3)"}

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.query.get("tags"):
            return await self.tag(scrape_item)
        if "posts" in scrape_item.url.parts:
            return await self.file(scrape_item)
        if "pools" in scrape_item.url.parts:
            return await self.pool(scrape_item)
        raise ValueError

    async def _pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[list[dict[str, Any]]]:
        """Generator for album pages."""
        initial_page = int(scrape_item.url.query.get("page", 1))
        url = PRIMARY_URL / "posts.json"
        for page in itertools.count(initial_page):
            url = url.with_query(tags=scrape_item.url.query["tags"], page=page)
            json_resp: dict[str, Any] = await self.request_json(url, headers=self.headers)
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

        async for posts in self._pager(scrape_item):
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
        url = PRIMARY_URL / f"pools/{pool_id}.json"
        json_resp: dict[str, Any] = await self.request_json(url, headers=self.headers)
        posts = json_resp.get("post_ids", [])
        title: str = json_resp.get("name", "Unknown Pool").replace("_", " ")
        scrape_item.setup_as_album(title)

        for post_id in posts:
            url = PRIMARY_URL / f"posts/{post_id}"
            new_scrape_item = scrape_item.create_child(url)
            self.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Fetches a single post by extracting the ID from the URL."""
        post_id = scrape_item.url.name
        url = PRIMARY_URL / f"posts/{post_id}.json"
        json_resp: dict[str, Any] = await self.request_json(url, headers=self.headers)
        try:
            file_url: str = json_resp["post"]["file"]["url"]
        except KeyError:
            raise ScrapeError(422) from None

        link = self.parse_url(file_url)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
