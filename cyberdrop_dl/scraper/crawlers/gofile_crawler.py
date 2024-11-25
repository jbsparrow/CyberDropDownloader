from __future__ import annotations

import contextlib
import http
import re
from copy import deepcopy
from hashlib import sha256
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import (
    DownloadError,
    MaxChildrenError,
    NoExtensionError,
    PasswordProtectedError,
    ScrapeError,
)
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.clients.scraper_client import ScraperClient
    from cyberdrop_dl.managers.manager import Manager


class GoFileCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "gofile", "GoFile")
        self.api_address = URL("https://api.gofile.io")
        self.js_address = URL("https://gofile.io/dist/js/alljs.js")
        self.primary_base_domain = URL("https://gofile.io")
        self.token = ""
        self.websiteToken = ""
        self.headers = {}
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        await self.get_token(self.api_address / "accounts", self.client)
        await self.get_website_token(self.js_address, self.client)

        await self.album(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        content_id = scrape_item.url.name
        scrape_item.album_id = content_id
        scrape_item.part_of_album = True

        password = scrape_item.url.query.get("password", "")
        scrape_item.url = scrape_item.url.with_query(None)
        if password:
            password = sha256(password.encode()).hexdigest()

        try:
            async with self.request_limiter:
                JSON_Resp = await self.client.get_json(
                    self.domain,
                    (self.api_address / "contents" / content_id).with_query(
                        {"wt": self.websiteToken, "password": password},
                    ),
                    headers_inc=self.headers,
                    origin=scrape_item,
                )
        except DownloadError as e:
            if e.status == http.HTTPStatus.UNAUTHORIZED:
                self.websiteToken = ""
                self.manager.cache_manager.remove("gofile_website_token")
                await self.get_website_token(self.js_address, self.client)
                async with self.request_limiter:
                    JSON_Resp = await self.client.get_json(
                        self.domain,
                        (self.api_address / "contents" / content_id).with_query(
                            {"wt": self.websiteToken, "password": password},
                        ),
                        headers_inc=self.headers,
                        origin=scrape_item,
                    )
            else:
                raise ScrapeError(e.status, e.message, origin=scrape_item) from None

        if JSON_Resp["status"] == "error-notFound":
            raise ScrapeError(404, "Album not found", origin=scrape_item)

        JSON_Resp: dict = JSON_Resp["data"]
        is_password_protected = JSON_Resp.get("password")
        if is_password_protected and (is_password_protected in {"passwordRequired", "passwordWrong"} or not password):
            raise PasswordProtectedError(origin=scrape_item)

        if JSON_Resp["canAccess"] is False:
            raise ScrapeError(403, "Album is private", origin=scrape_item)

        title = self.create_title(JSON_Resp["name"], content_id, None)
        # Do not reset nested folders
        if scrape_item.type != FILE_HOST_ALBUM:
            scrape_item.type = FILE_HOST_ALBUM
            scrape_item.children = scrape_item.children_limit = 0

            with contextlib.suppress(IndexError, TypeError):
                scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                    "maximum_number_of_children"
                ][scrape_item.type]

        contents = JSON_Resp["children"]
        for content_id in contents:
            content = contents[content_id]
            link = None
            if content["type"] == "folder":
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    self.primary_base_domain / "d" / content["code"],
                    title,
                    True,
                    add_parent=scrape_item.url,
                )
                self.manager.task_group.create_task(self.run(new_scrape_item))

            elif content["link"] == "overloaded":
                link = URL(content["directLink"])
            else:
                link = URL(content["link"])

            if link:
                try:
                    filename, ext = get_filename_and_ext(link.name)
                    duplicate_scrape_item = deepcopy(scrape_item)
                    duplicate_scrape_item.possible_datetime = content["createTime"]
                    duplicate_scrape_item.part_of_album = True
                    duplicate_scrape_item.add_to_parent_title(title)
                    await self.handle_file(link, duplicate_scrape_item, filename, ext)
                except NoExtensionError:
                    log(f"Scrape Failed: {link} (No File Extension)", 40)
                    await self.manager.log_manager.write_scrape_error_log(link, " No File Extension")
                    self.manager.progress_manager.scrape_stats_progress.add_failure("No File Extension")
            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def get_token(self, create_acct_address: URL, session: ScraperClient) -> None:
        """Get the token for the API."""
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
            return

        api_token = self.manager.config_manager.authentication_data["GoFile"]["gofile_api_key"]
        if api_token:
            self.token = api_token
            self.headers["Authorization"] = f"Bearer {self.token}"
            await self.set_cookie(session)
            return

        async with self.request_limiter:
            async with self.request_limiter:
                JSON_Resp = await session.post_data(self.domain, create_acct_address, data={})
            if JSON_Resp["status"] == "ok":
                self.token = JSON_Resp["data"]["token"]
                self.headers["Authorization"] = f"Bearer {self.token}"
                await self.set_cookie(session)
            else:
                raise ScrapeError(403, "Couldn't generate GoFile token")

    @error_handling_wrapper
    async def get_website_token(self, js_address: URL, session: ScraperClient) -> None:
        """Creates an anon gofile account to use."""
        if self.websiteToken:
            return

        website_token = self.manager.cache_manager.get("gofile_website_token")
        if website_token:
            self.websiteToken = website_token
            return

        async with self.request_limiter:
            text = await session.get_text(self.domain, js_address)
        text = str(text)
        self.websiteToken = re.search(r'fetchData\s=\s\{\swt:\s"(.*?)"', text).group(1)
        if not self.websiteToken:
            raise ScrapeError(403, "Couldn't generate GoFile websiteToken")
        self.manager.cache_manager.save("gofile_website_token", self.websiteToken)

    async def set_cookie(self, session: ScraperClient) -> None:
        """Sets the given token as a cookie into the session (and client)."""
        client_token = self.token
        morsel: http.cookies.Morsel = http.cookies.Morsel()
        morsel["domain"] = "gofile.io"
        morsel.set("accountToken", client_token, client_token)
        session.client_manager.cookies.update_cookies({"gofile.io": morsel})
