from __future__ import annotations

import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

HTML_RE = re.compile("<[^>]+>")
API_ENTRYPOINT = URL("https://a.4cdn.org/")
FILES_CDN = URL("https://i.4cdn.org/")
BOARDS_BASE_URL = URL("https://boards.4chan.org/")


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
        board = scrape_item.url.parts[1]
        thread = scrape_item.url.parts[-2]
        api_url = API_ENTRYPOINT / board / "thread" / f"{thread}.json"
        async with self.request_limiter:
            response = await self.client.get_json(self.domain, api_url, cache_disabled=True)
        if not response:
            raise ScrapeError(404)

        title = response["posts"][0].get("sub") or remove_html(response["posts"][0].get("com"))
        title = f"{title} [thread]"
        title = self.create_title(title)
        scrape_item.setup_as_album(title)

        for post in response["posts"]:
            if "filename" in post:
                file_id = post["tim"]
                filename, ext = self.get_filename_and_ext(f"{post['filename']}{post['ext']}")
                url = FILES_CDN / board / f"{file_id}{ext}"
                custom_filename, _ = self.get_filename_and_ext(url.name)
                scrape_item.possible_datetime = post["time"]
                if await self.check_complete_from_referer(url):
                    continue
                await self.handle_file(url, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def board(self, scrape_item: ScrapeItem) -> None:
        board: str = scrape_item.url.parts[-1]
        api_url = API_ENTRYPOINT / board / "threads.json"
        async with self.request_limiter:
            threads = await self.client.get_json(self.domain, api_url, cache_disabled=True)

        for page in threads:
            for thread in page["threads"]:
                url = BOARDS_BASE_URL / thread / thread["no"]
                new_scrape_item = scrape_item.create_child(url)
                self.manager.task_group.create_task(self.run(new_scrape_item))


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def remove_html(txt, repl=" ", sep=" "):
    """Remove html-tags from a string"""
    try:
        txt = HTML_RE.sub(repl, txt)
    except TypeError:
        return ""
    if sep:
        return sep.join(txt.split())
    return txt.strip()
