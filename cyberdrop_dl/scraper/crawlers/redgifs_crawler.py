from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class RedGifsCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "redgifs", "RedGifs")
        self.redgifs_api = URL("https://api.redgifs.com/")
        self.token = ""
        self.headers = {}
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if not self.token:
            await self.manage_token(self.redgifs_api / "v2/auth/temporary")

        if self.token:
            if "users" in scrape_item.url.parts:
                await self.user(scrape_item)
            else:
                await self.post(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a users page."""
        user_id = scrape_item.url.parts[-1].split(".")[0]

        page = 1
        total_pages = 1

        scrape_item.type = FILE_HOST_PROFILE
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]
        while page <= total_pages:
            async with self.request_limiter:
                JSON_Resp = await self.client.get_json(
                    self.domain,
                    (self.redgifs_api / "v2/users" / user_id / "search").with_query(f"order=new&count=40&page={page}"),
                    headers_inc=self.headers,
                    origin=scrape_item,
                )
            total_pages = JSON_Resp["pages"]
            gifs = JSON_Resp["gifs"]
            for gif in gifs:
                links = gif["urls"]
                date = gif["createDate"]
                title = self.create_title(user_id, None, None)

                try:
                    link = URL(links["hd"])
                except (KeyError, TypeError):
                    link = URL(links["sd"])

                filename, ext = get_filename_and_ext(link.name)
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    True,
                    date,
                    add_parent=scrape_item.url,
                )
                await self.handle_file(link, new_scrape_item, filename, ext)
                if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                    raise MaxChildrenError(origin=scrape_item)
            page += 1

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a post."""
        post_id = scrape_item.url.parts[-1].split(".")[0]

        async with self.request_limiter:
            JSON_Resp = await self.client.get_json(
                self.domain,
                self.redgifs_api / "v2/gifs" / post_id,
                headers_inc=self.headers,
                origin=scrape_item,
            )

        title_part = JSON_Resp["gif"].get("title", "Loose Files")
        title = self.create_title(title_part, None, None)
        links = JSON_Resp["gif"]["urls"]
        date = JSON_Resp["gif"]["createDate"]

        link = URL(links["hd"] if "hd" in links else links["sd"])

        filename, ext = get_filename_and_ext(link.name)
        new_scrape_item = self.create_scrape_item(
            scrape_item,
            link,
            title,
            True,
            date,
            add_parent=scrape_item.url,
        )
        await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def manage_token(self, token_url: URL) -> None:
        """Gets/Sets the redgifs token and header."""
        async with self.request_limiter:
            json_obj = await self.client.get_json(self.domain, token_url)
        self.token = json_obj["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
