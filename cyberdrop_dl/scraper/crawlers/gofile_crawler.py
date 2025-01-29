from __future__ import annotations

import http
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import DownloadError, PasswordProtectedError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
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
        self._website_token_date = datetime.now(UTC) - timedelta(days=7)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        get_website_token = error_handling_wrapper(self.get_website_token)
        await self.get_account_token(self.api)
        await get_website_token(self, self.primary_base_domain)

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        await self.album(scrape_item)

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

        content_query = {"wt": self.website_token, "password": password}
        content_url = self.api.joinpath("contents", content_id).with_query(content_query)
        api_query = {"url": content_url, "headers_inc": self.headers, "origin": scrape_item}

        try:
            async with self.request_limiter:
                json_resp = await self.client.get_json(self.domain, **api_query)

        except DownloadError as e:
            if e.status != http.HTTPStatus.UNAUTHORIZED:
                raise ScrapeError(e.status, e.message, origin=scrape_item) from e
            async with self.startup_lock:
                await self.get_website_token(update=True)
            content_url = content_url.update_query({"wt": self.website_token})
            api_query["url"] = content_url
            async with self.request_limiter:
                json_resp = await self.client.get_json(self.domain, **api_query)

        self.check_json_response(json_resp, scrape_item)
        title = self.create_title(json_resp["data"]["name"], content_id)
        scrape_item.add_to_parent_title(title)

        # Do not reset children inside nested folders
        if scrape_item.type != FILE_HOST_ALBUM:
            scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        children = json_resp["data"]["children"]
        await self.handle_children(children, scrape_item)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def check_json_response(self, json_resp: dict, scrape_item: ScrapeItem | None = None) -> None:
        """Parses and raises errors from json response."""
        if json_resp["status"] == "error-notFound":
            raise ScrapeError(404, origin=scrape_item)

        data: dict = json_resp["data"]
        is_password_protected = data.get("password")
        if is_password_protected and (is_password_protected in {"passwordRequired", "passwordWrong"}):
            raise PasswordProtectedError(origin=scrape_item)

        if not data.get("canAccess"):
            raise ScrapeError(403, "Album is private", origin=scrape_item)

    async def handle_children(self, children: dict, scrape_item: ScrapeItem) -> None:
        """Sends files to downloader and adds subfolder to scrape queue."""
        subfolders = []
        for child in children.values():
            if child["type"] == "folder":
                folder_url = self.primary_base_domain / "d" / child["code"]
                subfolders.append(folder_url)
                continue

            link_str = child["link"]
            if link_str == "overloaded":
                link_str = child["directLink"]

            link = self.parse_url(link_str)
            date = child["createTime"]
            filename, ext = get_filename_and_ext(link.name)
            new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)
            await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.add_children()

        for folder_url in subfolders:
            subfolder = self.create_scrape_item(scrape_item, url=folder_url, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(subfolder))

    @error_handling_wrapper
    async def get_account_token(self, _) -> None:
        """Gets the token for the API."""
        self.api_key = self.api_key or await self._get_new_api_key()
        self.headers["Authorization"] = f"Bearer {self.api_key}"
        cookies = {"accountToken": self.api_key}
        self.update_cookies(cookies)

    async def _get_new_api_key(self) -> str:
        create_account_address = self.api / "accounts"
        async with self.request_limiter:
            json_resp = await self.client.post_data(self.domain, create_account_address, data={})
        if json_resp["status"] != "ok":
            raise ScrapeError(401, "Couldn't generate GoFile API token", origin=create_account_address)

        return json_resp["data"]["token"]

    async def get_website_token(self, _: ScrapeItem | URL | None = None, update: bool = False) -> None:
        """Creates an anon GoFile account to use."""
        if datetime.now(UTC) - self._website_token_date < timedelta(seconds=120):
            return
        if update:
            self.website_token = ""
            self.manager.cache_manager.remove("gofile_website_token")
        if self.website_token:
            return
        await self._update_website_token()

    async def _update_website_token(self) -> None:
        async with self.request_limiter:
            text = await self.client.get_text(self.domain, self.js_address, origin=self.js_address)
        match = re.search(WT_REGEX, str(text))
        if not match:
            raise ScrapeError(401, "Couldn't generate GoFile websiteToken", origin=self.js_address)
        self.website_token = match.group(1)
        self.manager.cache_manager.save("gofile_website_token", self.website_token)
        self._website_token_date = datetime.now(UTC)
