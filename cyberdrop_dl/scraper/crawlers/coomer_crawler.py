from __future__ import annotations

import calendar
import contextlib
import datetime
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


@dataclass
class Post:
    id: int
    title: str
    date: int

    @property
    def number(self):
        return self.id


class CoomerCrawler(Crawler):
    primary_base_domain = URL("https://coomer.su")
    DEFAULT_POST_TITLE_FORMAT = "{date} - {title}"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "coomer", "Coomer")
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
        if not self.manager.config_manager.authentication_data.coomer.session:
            raise ScrapeError(
                401,
                message="No session cookie found in the config file, cannot scrape favorites",
                origin=scrape_item,
            )
        async with self.request_limiter:
            # Use the session cookie to get the user's favourites
            self.client.client_manager.cookies.update_cookies(
                {"session": self.manager.config_manager.authentication_data.coomer.session},
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
        user_info: dict[str, str] = await self.get_user_info(scrape_item)
        service, user, user_str = user_info["service"], user_info["user"], user_info["user_str"]
        offset, maximum_offset, post_limit = user_info["offset"], user_info["maximum_offset"], user_info["limit"]
        api_call = self.api_url / service / "user" / user
        scrape_item.type = FILE_HOST_PROFILE
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = (
                self.manager.config_manager.settings_data.download_options.maximum_number_of_children[scrape_item.type]
            )

        while offset <= maximum_offset:
            async with self.request_limiter:
                query_api_call = api_call.with_query({"o": offset})
                JSON_Resp = await self.client.get_json(
                    self.domain,
                    query_api_call,
                    origin=scrape_item,
                )
                offset += post_limit
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
        user_info = await self.get_user_info(scrape_item)
        service, user, user_str, post_id = (
            user_info["service"],
            user_info["user"],
            user_info["user_str"],
            user_info["post"],
        )
        api_call = self.api_url / service / "user" / user / "post" / post_id
        async with self.request_limiter:
            post: dict = await self.client.get_json(self.domain, api_call, origin=scrape_item)
            post = post.get("post")
        await self.handle_post_content(scrape_item, post, user, user_str)

    @error_handling_wrapper
    async def handle_post_content(self, scrape_item: ScrapeItem, post: dict, user: str, user_str: str) -> None:
        """Handles the content of a post."""
        if "#ad" in post["content"] and self.manager.config_manager.settings_data.ignore_options.ignore_coomer_ads:
            return

        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = (
                self.manager.config_manager.settings_data.download_options.maximum_number_of_children[scrape_item.type]
            )

        date: str = post.get("published") or post.get("added")
        date = date.replace("T", " ")
        post_id = post["id"]
        post_title = post["title"]

        scrape_item.album_id = post_id
        scrape_item.part_of_album = True
        if not post_title:
            post_title = "Untitled"

        async def handle_file(file_obj: dict):
            link: URL = self.primary_base_domain / ("data" + file_obj["path"])
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
        filename, ext = get_filename_and_ext(scrape_item.url.query.get("f") or scrape_item.url.name)
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
        post = Post(id=post_id, title=title, date=date)
        new_title = self.create_title(user, None, None)
        new_scrape_item = self.create_scrape_item(
            old_scrape_item,
            link,
            new_title,
            True,
            None,
            post.date,
            add_parent=add_parent,
        )
        self.add_separate_post_title(new_scrape_item, post)
        await self.handle_direct_link(new_scrape_item)

    async def get_user_info(self, scrape_item: ScrapeItem) -> dict:
        """Gets the user info from a scrape item."""
        user = scrape_item.url.parts[3]
        service = scrape_item.url.parts[1]
        try:
            post = scrape_item.url.parts[5]
        except IndexError:
            post = None

        profile_api_url = self.api_url / service / "user" / user / "posts-legacy"
        async with self.request_limiter:
            profile_json, resp = await self.client.get_json(
                self.domain, profile_api_url, origin=scrape_item, cache_disabled=True
            )
            properties: dict = profile_json.get("props", {})
            cached_response = await self.manager.cache_manager.request_cache.get_response(str(profile_api_url))
            cached_properties = {} if not cached_response else (await cached_response.json()).get("props", {})

            # Shift cache offsets if necessary
            await self.shift_offsets(profile_api_url, properties, cached_properties, resp)

        limit = properties.get("limit", 50)
        user_str = properties.get("name", user)
        if post:
            offset, maximum_offset = None, None
        else:
            offset = int(scrape_item.url.query.get("o", 0))
            maximum_offset = maximum_offset = (int(properties.get("count", 0)) // limit) * limit

        return {
            "service": service,
            "user": user,
            "post": post,
            "user_str": user_str,
            "offset": offset,
            "maximum_offset": maximum_offset,
            "limit": limit,
        }

    async def shift_offsets(self, api_url: URL, new_properties: dict, cached_properties: dict, response) -> None:
        """
        Adjust cached responses for shifted offsets based on the difference in the number of posts.

        Args:
            api_url (URL): The legacy API URL.
            new_properties (dict): Properties from the current response.
            cached_properties (dict): Properties from the cached response.
            response: The latest HTTP response to save to the cache.

        Returns:
            int: The updated maximum offset.
        """
        user_str = new_properties.get("name", "Unknown")
        new_count = int(new_properties.get("count", 0))
        cached_count = int(cached_properties.get("count", 0))
        if cached_count == 0:
            return
        post_limit = int(new_properties.get("limit", 50))
        shift = new_count - cached_count

        if shift > 0:
            log(f"{shift} new posts detected for {user_str} (Coomer). Adjusting cache...", 20)

            cached_posts = []
            offset = 0
            invalidate = False
            max_offset = (new_count // post_limit) * post_limit
            for offset in range(0, max_offset + 1, post_limit):
                paginated_api_url = api_url.with_query({"o": offset})
                cache_key = self.manager.cache_manager.request_cache.create_key("GET", paginated_api_url)
                cached_response = await self.manager.cache_manager.request_cache.get_response(cache_key)

                if not cached_response:
                    invalidate = True
                    continue
                else:
                    cached_json = await cached_response.json()
                    if len(cached_json) < post_limit and offset != max_offset:
                        invalidate = True

                if invalidate:
                    await self.manager.cache_manager.request_cache.delete_url(cache_key)
                    log(f"Invalidated cached page: {paginated_api_url}", 20)
                    continue

                cached_json = await cached_response.json()
                cached_posts.extend(cached_json)

            all_posts = ["placeholder"] * shift + cached_posts
            new_pages = [all_posts[i : i + post_limit] for i in range(0, len(all_posts), post_limit)]

            for page_index, page_posts in enumerate(new_pages):
                offset = page_index * post_limit
                paginated_api_url = api_url.with_query({"o": offset})
                cache_key = self.manager.cache_manager.request_cache.create_key("GET", paginated_api_url)

                if "placeholder" in page_posts:
                    # Invalidate cache for this page
                    await self.manager.cache_manager.request_cache.delete_url(cache_key)
                    log(f"Invalidated cached page: {paginated_api_url}", 20)
                else:
                    cached_response = await self.manager.cache_manager.request_cache.get_response(cache_key)
                    if cached_response:
                        # Update the cached response
                        adjusted_content = json.dumps(page_posts).encode("utf-8")
                        cached_response._body = adjusted_content
                        cached_response.reset()

                        await self.manager.cache_manager.request_cache.save_response(
                            cached_response,
                            cache_key,
                            datetime.datetime.now()
                            + self.manager.config_manager.global_settings_data.rate_limiting_options.file_host_cache_expire_after,
                        )

            legacy_cache_key = self.manager.cache_manager.request_cache.create_key("GET", api_url)
            await self.manager.cache_manager.request_cache.save_response(
                response,
                legacy_cache_key,
                datetime.datetime.now()
                + self.manager.config_manager.global_settings_data.rate_limiting_options.file_host_cache_expire_after,
            )

        return

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())
