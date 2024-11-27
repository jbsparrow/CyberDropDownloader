from __future__ import annotations

import calendar
import contextlib
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class CoomerCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "coomer", "Coomer")
        self.primary_base_domain = URL("https://coomer.su")
        self.ddos_guard_domain = URL("https://*.coomer.su")
        self.api_url = URL("https://coomer.su/api/v1")
        self.request_limiter = AsyncLimiter(4, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "thumbnails" in scrape_item.url.parts:
            parts = [x for x in scrape_item.url.parts if x not in ("thumbnail", "/")]
            link = URL(f"https://{scrape_item.url.host}/{'/'.join(parts)}")
            scrape_item.url = link
            await self.handle_direct_link(scrape_item)
        elif "post" in scrape_item.url.parts:
            await self.post(scrape_item)
        elif "onlyfans" in scrape_item.url.parts or "fansly" in scrape_item.url.parts:
            await self.profile(scrape_item)
        elif "favorites" in scrape_item.url.parts:
            await self.favorites(scrape_item)
        else:
            await self.handle_direct_link(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def favorites(self, scrape_item: ScrapeItem) -> None:
        """Scrapes the users' favourites and creates scrape items for each artist found."""
        if not self.manager.config_manager.authentication_data["Coomer"]["session"]:
            raise ScrapeError(
                401,
                message="No session cookie found in the config file, cannot scrape favorites",
                origin=scrape_item,
            )
        async with self.request_limiter:
            # Use the session cookie to get the user's favourites
            self.client.client_manager.cookies.update_cookies(
                {"session": self.manager.config_manager.authentication_data["Coomer"]["session"]},
                response_url=self.primary_base_domain,
            )
            favourites_api_url = (self.api_url / "account/favorites").with_query({"type": "artist"})
            JSON_Resp = await self.client.get_json(self.domain, favourites_api_url, origin=scrape_item)
            self.client.client_manager.cookies.update_cookies({"session": ""}, response_url=self.primary_base_domain)
            for user in JSON_Resp:
                id = user["id"]
                service = user["service"]
                url = self.primary_base_domain / service / "user" / id
                new_scrape_item = self.create_scrape_item(scrape_item, url, None, True, None, None)
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        offset = 0
        service, user, user_str = await self.get_user_info(scrape_item)
        api_call = self.api_url / service / "user" / user
        scrape_item.type = FILE_HOST_PROFILE
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        while True:
            async with self.request_limiter:
                JSON_Resp = await self.client.get_json(
                    self.domain,
                    api_call.with_query({"o": offset}),
                    origin=scrape_item,
                )
                offset += 50
                if not JSON_Resp:
                    break

            for post in JSON_Resp:
                await self.handle_post_content(scrape_item, post, user, user_str)
                scrape_item.children += 1
                if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                    raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a post."""
        service, user, post_id, user_str = await self.get_user_info(scrape_item)
        api_call = self.api_url / service / "user" / user / "post" / post_id
        async with self.request_limiter:
            post = await self.client.get_json(self.domain, api_call, origin=scrape_item)
            post = post.get("post")
        await self.handle_post_content(scrape_item, post, user, user_str)

    @error_handling_wrapper
    async def handle_post_content(self, scrape_item: ScrapeItem, post: dict, user: str, user_str: str) -> None:
        """Handles the content of a post."""
        if (
            "#ad" in post["content"]
            and self.manager.config_manager.settings_data["Ignore_Options"]["ignore_coomer_ads"]
        ):
            return

        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        date = post.get("published") or post.get("added")
        date = date.replace("T", " ")
        post_id = post["id"]
        post_title = post["title"]

        scrape_item.album_id = post_id
        scrape_item.part_of_album = True
        if not post_title:
            post_title = "Untitled"

        async def handle_file(file_obj: dict):
            link = self.primary_base_domain / ("data" + file_obj["path"])
            link = link.with_query({"f": file_obj["name"]})
            await self.create_new_scrape_item(
                link,
                scrape_item,
                user_str,
                post_title,
                post_id,
                date,
                add_parent=scrape_item.url.joinpath("post", post_id),
            )

        files = []
        if post.get("file"):
            files.append(post["file"])

        if post.get("attachments"):
            files.extend(post["attachments"])

        for file in files:
            await handle_file(file)
            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        try:
            filename, ext = get_filename_and_ext(scrape_item.url.query["f"])
        except KeyError:
            filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def create_new_scrape_item(
        self,
        link: URL,
        old_scrape_item: ScrapeItem,
        user: str,
        title: str,
        post_id: str,
        date: str,
        add_parent: URL | None = None,
    ) -> None:
        """Creates a new scrape item with the same parent as the old scrape item."""
        post_title = None
        if self.manager.config_manager.settings_data["Download_Options"]["separate_posts"]:
            post_title = f"{date} - {title}"
            if self.manager.config_manager.settings_data["Download_Options"]["include_album_id_in_folder_name"]:
                post_title = post_id + " - " + post_title

        new_title = self.create_title(user, None, None)
        new_scrape_item = self.create_scrape_item(
            old_scrape_item,
            link,
            new_title,
            True,
            None,
            self.parse_datetime(date),
            add_parent=add_parent,
        )
        new_scrape_item.add_to_parent_title(post_title)
        self.manager.task_group.create_task(self.run(new_scrape_item))

    async def get_user_info(self, scrape_item: ScrapeItem) -> tuple[str, str, str, str]:
        """Gets the user info from a scrape item."""
        user = scrape_item.url.parts[3]
        service = scrape_item.url.parts[1]
        try:
            post = scrape_item.url.parts[5]
        except IndexError:
            post = None
        profile_api_url = self.api_url / service / "user" / user / "profile"
        async with self.request_limiter:
            profile_json: dict = await self.client.get_json(self.domain, profile_api_url, origin=scrape_item)
        if post:
            return service, user, post, profile_json["name"]
        return service, user, profile_json["name"]

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string."""
        date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(date.timetuple())
