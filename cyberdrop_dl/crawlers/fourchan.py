from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict, cast

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

API_ENTRYPOINT = URL("https://a.4cdn.org/")
FILES_BASE_URL = URL("https://i.4cdn.org/")


class Post(TypedDict):
    sub: NotRequired[str]  # Subject
    com: NotRequired[str]  # Comment
    time: int  # Unix timestamp


class ImagePost(Post):
    filename: str  # File stem
    ext: str
    tim: int  # Unix timestamp + microtime of uploaded image


class Thread(TypedDict):
    no: int  # Original post ID


class ThreadList(TypedDict):
    page: int
    threads: list[Thread]


class FourChanCrawler(Crawler):
    primary_base_domain = URL("https://boards.4chan.org")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "4chan", "4chan")
        self.request_limiter = AsyncLimiter(3, 10)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "thread" in scrape_item.url.parts:
            return await self.thread(scrape_item)
        elif len(scrape_item.url.parts) == 2:
            return await self.board(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def thread(self, scrape_item: ScrapeItem) -> None:
        board, _, thread_id = scrape_item.url.parts[1:4]
        api_url = API_ENTRYPOINT / board / f"thread/{thread_id}.json"
        async with self.request_limiter:
            response: dict[str, list[Post]] = await self.client.get_json(self.domain, api_url, cache_disabled=True)
        if not response:
            raise ScrapeError(404)

        original_post = response["posts"][0]
        if subject := original_post.get("sub"):
            title: str = subject
        elif comment := original_post.get("com"):
            title = BeautifulSoup(comment).get_text(strip=True)
        else:
            title = f"#{thread_id}"
        title = self.create_title(f"{title} [thread]", thread_id)
        scrape_item.setup_as_album(title, album_id=thread_id)
        results = await self.get_album_results(thread_id)

        for post in response["posts"]:
            if file_stem := post.get("filename"):
                post = cast("ImagePost", post)
                file_micro_timestamp, ext = post["tim"], post["ext"]
                url = FILES_BASE_URL / board / f"{file_micro_timestamp}{ext}"
                if self.check_album_results(url, results):
                    continue

                custom_filename, ext = self.get_filename_and_ext(f"{file_stem}{ext}")
                filename, _ = self.get_filename_and_ext(url.name)
                new_scrape_item = scrape_item.copy()
                new_scrape_item.possible_datetime = post["time"]
                await self.handle_file(url, new_scrape_item, filename, ext, custom_filename=custom_filename)
                scrape_item.add_children()

    @error_handling_wrapper
    async def board(self, scrape_item: ScrapeItem) -> None:
        board: str = scrape_item.url.parts[-1]
        api_url = API_ENTRYPOINT / board / "threads.json"
        async with self.request_limiter:
            threads: list[ThreadList] = await self.client.get_json(self.domain, api_url, cache_disabled=True)

        scrape_item.setup_as_forum("")
        for page in threads:
            for thread in page["threads"]:
                url = self.primary_base_domain / board / f"thread/{thread['no']}"
                new_scrape_item = scrape_item.create_child(url)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()
