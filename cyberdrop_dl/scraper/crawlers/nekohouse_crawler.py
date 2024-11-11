from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem


class NekohouseCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "nekohouse", "Nekohouse")
        self.primary_base_domain = URL("https://nekohouse.su")
        self.services = ["fanbox", "fantia", "fantia_products", "subscribestar", "twitter"]
        self.request_limiter = AsyncLimiter(10, 1)

        self.post_selector = "article.post-card a"
        self.post_content_selector = "div[class=scrape__files]"
        self.file_downloads_selector = "a[class=scrape__attachment-link]"
        self.post_images_selector = "div[class=fileThumb]"
        self.post_videos_selector = "video[class=post__video] source"
        self.post_timestamp_selector = "time[class=timestamp ]"
        self.post_title_selector = "h1[class=scrape__title] span"
        self.post_content_selector = "div[class=scrape__content]"
        self.post_author_username_selector = "a[class=scrape__user-name]"

        self.maximum_offset = 0

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
            if "user" not in scrape_item.url.parts:
                user = "Unknown"
                post_id = scrape_item.url.parts[-1]
                service = "Unknown"
                user_str = "Unknown"
                await self.post(scrape_item, post_id, user, service, user_str, unlinked_post=True)
            else:
                await self.post(scrape_item)
        elif any(x in scrape_item.url.parts for x in self.services):
            await self.profile(scrape_item)
        else:
            await self.handle_direct_link(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        offset, maximum_offset = await self.get_offsets(scrape_item, soup)
        service, user = self.get_service_and_user(scrape_item)
        user_str = await self.get_user_str_from_profile(soup)
        service_call = self.primary_base_domain / service / "user" / user
        while offset <= maximum_offset:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(
                    self.domain,
                    service_call.with_query({"o": offset}),
                    origin=scrape_item,
                )
                offset += 50

                posts = soup.select(self.post_selector)
                if not posts:
                    break
                for post in posts:
                    # Create a new scrape item for each post
                    post_url = post.get("href", "")
                    if post_url[0] == "/":
                        post_url = post_url[1:]
                    post_id = post_url.split("/")[-1]
                    if post_url == "":
                        continue
                    post_link = self.primary_base_domain / post_url
                    # Call on self.post to scrape the post by creating a new scrape item
                    new_scrape_item = self.create_scrape_item(
                        scrape_item,
                        post_link,
                        "",
                        add_parent=self.primary_base_domain / service / "user" / user,
                    )
                    await self.post(new_scrape_item, post_id, user, service, user_str)

    @error_handling_wrapper
    async def post(
        self,
        scrape_item: ScrapeItem,
        post_id: int | None = None,
        user: str | None = None,
        service: str | None = None,
        user_str: str | None = None,
        unlinked_post: bool = False,
    ) -> None:
        """Scrapes a post."""
        if any(x is None for x in (post_id, user, service, user_str)):
            service, user, post_id = await self.get_service_user_and_post(scrape_item)
            user_str = await self.get_user_str_from_post(scrape_item)
        await self.get_post_content(scrape_item, post_id, user, service, user_str, unlinked_post)

    @error_handling_wrapper
    async def get_post_content(
        self,
        scrape_item: ScrapeItem,
        post: int,
        user: str,
        service: str,
        user_str: str,
        unlinked_post: bool = False,
    ) -> None:
        """Gets the content of a post and handles collected links."""
        if post == 0:
            return

        post_url = scrape_item.url
        if unlinked_post is True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, post_url, origin=scrape_item)
                data = {
                    "id": post,
                    "user": user,
                    "service": service,
                    "title": "",
                    "content": "",
                    "user_str": user_str,
                    "published": "",
                    "file": [],
                    "attachments": [],
                }

                try:
                    data["title"] = soup.select_one(self.post_title_selector).text.strip()
                except AttributeError:
                    msg = "Failed to scrape post title."
                    raise ScrapeError(msg) from None
                try:
                    data["content"] = soup.select_one(self.post_content_selector).text.strip()
                except AttributeError:
                    msg = "Failed to scrape post content."
                    raise ScrapeError(msg) from None
                try:
                    data["published"] = soup.select_one(self.post_timestamp_selector).text.strip()
                except AttributeError:
                    msg = "Failed to scrape post timestamp."
                    raise ScrapeError(msg) from None

                for file in soup.select(self.post_images_selector):
                    attachment = {
                        "path": file["href"].replace("/data/", "data/"),
                        "name": file["href"].split("?f=")[-1]
                        if "?f=" in file["href"]
                        else file["href"].split("/")[-1].split("?")[0],
                    }
                    data["attachments"].append(attachment)

                for file in soup.select(self.post_videos_selector):
                    attachment = {
                        "path": file["src"].replace("/data/", "data/"),
                        "name": file["src"].split("?f=")[-1]
                        if "?f=" in file["src"]
                        else file["src"].split("/")[-1].split("?")[0],
                    }
                    data["attachments"].append(attachment)

                for file in soup.select(self.file_downloads_selector):
                    attachment = {
                        "path": file["href"].replace("/data/", "data/"),
                        "name": file["href"].split("?f=")[-1]
                        if "?f=" in file["href"]
                        else file["href"].split("/")[-1].split("?")[0],
                    }
                    data["file"].append(attachment)
        else:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, post_url, origin=scrape_item)
                # Published as current time to avoid errors.
                data = {
                    "id": post,
                    "user": user,
                    "service": service,
                    "title": "",
                    "content": "Unknown",
                    "user_str": user_str,
                    "published": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "file": [],
                    "attachments": [],
                }

                try:
                    data["title"] = soup.select_one("title").text.strip()
                except AttributeError:
                    msg = "Failed to scrape post title."
                    raise ScrapeError(msg) from None

                for file in soup.select("a[class=post__attachment-link]"):
                    attachment = {
                        "path": file["href"].replace("/data/", "data/"),
                        "name": file["href"].split("?f=")[-1]
                        if "?f=" in file["href"]
                        else file["href"].split("/")[-1].split("?")[0],
                    }
                    data["attachments"].append(attachment)

        await self.handle_post_content(scrape_item, data, user, user_str)

    @error_handling_wrapper
    async def handle_post_content(self, scrape_item: ScrapeItem, post: dict, user: str, user_str: str) -> None:
        """Handles the content of a post."""
        date = post["published"].replace("T", " ")
        post_id = post["id"]
        post_title = post.get("title", "")

        scrape_item.album_id = post_id
        scrape_item.part_of_album = True

        async def handle_file(file_obj: dict):
            link = self.primary_base_domain / file_obj["path"]
            link = link.with_query({"f": file_obj["name"]})
            await self.create_new_scrape_item(link, scrape_item, user_str, post_title, post_id, date)

        for file in post["attachments"]:
            await handle_file(file)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        try:
            filename, ext = get_filename_and_ext(scrape_item.url.query["f"])
        except NoExtensionError:
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

    async def get_maximum_offset(self, soup: BeautifulSoup) -> int:
        """Gets the maximum offset for a scrape item."""
        menu = soup.select_one("menu")
        if menu is None:
            self.maximum_offset = 0
            return 0
        try:
            max_tabs = (
                (int(soup.select_one("div[id=paginator-top] small").text.strip().split(" ")[-1]) + 49) // 50
            ) * 50
        except AttributeError:
            max_tabs = 0
        pagination_links = menu.find_all("a", href=True)
        offsets = [int(x["href"].split("?o=")[-1]) for x in pagination_links]
        offset = max(offsets)
        offset = max(max_tabs, offset)
        self.maximum_offset = offset
        return offset

    async def get_offsets(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> tuple[int, int]:
        """Gets the offset for a scrape item."""
        current_offset = int(scrape_item.url.query.get("o", 0))
        maximum_offset = await self.get_maximum_offset(soup)
        return current_offset, maximum_offset

    @error_handling_wrapper
    async def get_user_str_from_post(self, scrape_item: ScrapeItem) -> str:
        """Gets the user string from a scrape item."""
        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        return soup.select_one("a[class=scrape__user-name]").text

    @error_handling_wrapper
    async def get_user_str_from_profile(self, soup: BeautifulSoup) -> str:
        """Gets the user string from a scrape item."""
        return soup.select_one("span[itemprop=name]").text

    @staticmethod
    def get_service_and_user(scrape_item: ScrapeItem) -> tuple[str, str]:
        """Gets the service and user from a scrape item."""
        user = scrape_item.url.parts[3]
        service = scrape_item.url.parts[1]
        return service, user

    @staticmethod
    async def get_service_user_and_post(scrape_item: ScrapeItem) -> tuple[str, str, str]:
        """Gets the service, user and post id from a scrape item."""
        user = scrape_item.url.parts[3]
        service = scrape_item.url.parts[1]
        post = scrape_item.url.parts[5]
        return service, user, post

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        try:
            date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")
        return calendar.timegm(date.timetuple())
