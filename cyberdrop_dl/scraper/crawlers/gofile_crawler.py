from __future__ import annotations

import contextlib
import http
import re
from hashlib import sha256
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import (
    DownloadError,
    MaxChildrenError,
    PasswordProtectedError,
    ScrapeError,
)
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


WT_REGEX = re.compile(r'appdata\.wt\s=\s"([^"]+)"')


class GoFileCrawler(Crawler):
    primary_base_domain = URL("https://gofile.io")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "gofile", "GoFile")
        self.api = URL("https://api.gofile.io")
        self.js_address = URL("https://gofile.io/dist/js/global.js")
        self.api_key = manager.config_manager.authentication_data.gofile.api_key
        self.website_token = manager.cache_manager.get("gofile_website_token")
        self.headers = {}
        self.request_limiter = AsyncLimiter(100, 60)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        await self.get_account_token(scrape_item)
        await self.get_website_token(scrape_item)
        await self.album(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        if not self.api_key or not self.website_token:
            return
        content_id = scrape_item.url.name
        scrape_item.album_id = content_id
        scrape_item.part_of_album = True
        password = scrape_item.url.query.get("password", "")
        scrape_item.url = scrape_item.url.with_query(None)
        if password:
            password = sha256(password.encode()).hexdigest()

        content_url = self.api.joinpath("contents", content_id).with_query(
            {"wt": self.website_token, "password": password}
        )

        api_query = {"url": content_url, "headers_inc": self.headers, "origin": scrape_item}

        try:
            async with self.request_limiter:
                json_resp = await self.client.get_json(self.domain, **api_query)

        except DownloadError as e:
            if e.status != http.HTTPStatus.UNAUTHORIZED:
                raise ScrapeError(e.status, e.message, origin=scrape_item) from e
            await self.get_website_token(update=True)
            content_url = content_url.update_query({"wt": self.website_token})
            api_query["url"] = content_url
            async with self.request_limiter:
                json_resp = await self.client.get_json(self.domain, **api_query)

        self.check_json_response(json_resp, scrape_item)
        title = self.create_title(json_resp["data"]["name"], content_id, None)
        scrape_item.add_to_parent_title(title)

        # Do not reset children inside nested folders
        if scrape_item.type != FILE_HOST_ALBUM:
            scrape_item.type = FILE_HOST_ALBUM
            scrape_item.children = scrape_item.children_limit = 0

            with contextlib.suppress(IndexError, TypeError):
                scrape_item.children_limit = (
                    self.manager.config_manager.settings_data.download_options.maximum_number_of_children[
                        scrape_item.type
                    ]
                )

        children = json_resp["data"]["children"]
        await self.handle_children(children, scrape_item)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def check_json_response(self, json_resp: dict, scrape_item: ScrapeItem | None = None) -> None:
        """Parses and raises errors from json response."""
        if json_resp["status"] == "error-notFound":
            raise ScrapeError(404, origin=scrape_item)

        json_resp: dict = json_resp["data"]
        is_password_protected = json_resp.get("password")
        if is_password_protected and (is_password_protected in {"passwordRequired", "passwordWrong"}):
            raise PasswordProtectedError(origin=scrape_item)

        if not json_resp.get("canAccess"):
            raise ScrapeError(403, "Album is private", origin=scrape_item)

    async def handle_children(self, children: dict, scrape_item: ScrapeItem) -> None:
        """Sends files to downloader and adds subfolder to scrape queue."""
        subfolders = []
        for child in children.values():
            if child["type"] == "folder":
                child_url = self.primary_base_domain / "d" / child["code"]
                new_scrape_item = self.create_scrape_item(scrape_item, url=child_url, add_parent=scrape_item.url)
                subfolders.append(new_scrape_item)
                continue

            link = URL(child["link"])
            if child["link"] == "overloaded":
                link = URL(child["directLink"])
            filename, ext = get_filename_and_ext(link.name)
            new_scrape_item = self.create_scrape_item(
                scrape_item, scrape_item.url, possible_datetime=child["createTime"]
            )
            await self.handle_file(link, new_scrape_item, filename, ext)

            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

        for subfolder in subfolders:
            self.manager.task_group.create_task(self.run(subfolder))

    @error_handling_wrapper
    async def get_account_token(self, scrape_item: ScrapeItem) -> None:
        """Gets the token for the API."""
        if not self.api_key:
            create_account_address = self.api / "accounts"
            async with self.request_limiter:
                json_resp = await self.client.post_data(self.domain, create_account_address, data={})
                if json_resp["status"] != "ok":
                    raise ScrapeError(401, "Couldn't generate GoFile API token", origin=scrape_item)

            self.api_key = json_resp["data"]["token"]
        self.headers["Authorization"] = f"Bearer {self.api_key}"
        self.client.client_manager.cookies.update_cookies(
            {"accountToken": self.api_key}, response_url=self.primary_base_domain
        )

    @error_handling_wrapper
    async def get_website_token(self, scrape_item: ScrapeItem, update: bool = False) -> None:
        """Creates an anon GoFile account to use."""
        if update:
            self.website_token = ""
            self.manager.cache_manager.remove("gofile_website_token")
        if self.website_token:
            return
        async with self.request_limiter:
            text = await self.client.get_text(self.domain, self.js_address, origin=scrape_item)
        match = re.search(WT_REGEX, str(text))
        if not match:
            raise ScrapeError(401, "Couldn't generate GoFile websiteToken", origin=scrape_item)
        self.website_token = match.group(1)
        self.manager.cache_manager.save("gofile_website_token", self.website_token)
