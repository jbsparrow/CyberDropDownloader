from __future__ import annotations

import calendar
import itertools
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import AliasPath, Field, PlainValidator
from yarl import URL

from cyberdrop_dl.config_definitions.custom.types import AliasModel
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, parse_url

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

API_ENTRYPOINT = URL("https://api.fikfap.com")
PRIMARY_BASE_DOMAIN = URL("https://fikfak.com")
AMOUNT_LIMIT = 40  # Requesting more posts that this will return 400 - Bad Request

HttpURL = Annotated[URL, PlainValidator(parse_url)]


class Post(AliasModel):
    label: str
    id: str = Field(alias="postId", coerce_numbers_to_str=True)
    user_id: str = Field(alias="userId")
    media_id: str = Field(alias="mediaId")
    created_at: datetime = Field(alias="createdAt")
    stream_url: HttpURL = Field(alias="videoStreamUrl")
    user: str = Field(validation_alias=AliasPath("author", "username"))

    @property
    def page_url(self) -> URL:
        return PRIMARY_BASE_DOMAIN / "posts" / self.id

    @property
    def timestamp(self) -> int:
        return calendar.timegm(self.created_at.timetuple())


class FikFapCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "fikfap", "FikFap")
        self.id_token = ""
        self.headers = {"Authorization-Anonymous": self.id_token}

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        # Check post first because they can match all the other paths:
        # https://fikfap.com/hash/hats/post/123456
        # https://fikfap.com/post/851604,
        # https://fikfap.com/user/alinevs/post/1068195
        if "post" in scrape_item.url.parts:
            return await self.post(scrape_item)
        if "user" in scrape_item.url.parts:
            return await self.user(scrape_item)
        if "hash" in scrape_item.url.parts:
            return await self.hashtag(scrape_item)
        if "search" in scrape_item.url.parts and scrape_item.url.query.get("q"):
            return await self.search(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        post_id = scrape_item.url.name
        canonical_url = PRIMARY_BASE_DOMAIN / "posts" / post_id
        if await self.check_complete_from_referer(canonical_url):
            return
        api_url = API_ENTRYPOINT / "posts" / post_id
        headers = self.headers | {"Referer": str(scrape_item.url)}
        async with self.request_limiter:
            json_resp: dict[str, Any] = await self.client.get_json(self.domain, api_url, headers_inc=headers)

        post = Post(**json_resp)
        await self.handle_post(scrape_item, post)

    async def user(self, scrape_item: ScrapeItem) -> None:
        user_name = scrape_item.url.name
        api_url = API_ENTRYPOINT / "profile/username" / user_name / "posts"
        api_url = api_url.with_query(amount=AMOUNT_LIMIT)
        # Title will be added by self.handle_post, This is just to set `max_children_limit`
        scrape_item.setup_as_profile("")
        await self.collection(scrape_item, api_url)

    async def hashtag(self, scrape_item: ScrapeItem) -> None:
        label = scrape_item.url.name
        api_url = API_ENTRYPOINT / "hashtags/label" / label / "posts"
        api_url = api_url.with_query(amount=AMOUNT_LIMIT, topPercentage=33)
        title = self.create_title(f"{label} [hashtag]")
        scrape_item.setup_as_album(title)
        await self.collection(scrape_item, api_url)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem):
        search_query = scrape_item.url.query["q"]
        api_url = API_ENTRYPOINT / "search"
        api_url = api_url.with_query(q=search_query, amount=AMOUNT_LIMIT)
        headers = self.headers | {"Referer": str(scrape_item.url)}
        title = self.create_title(f"{search_query} [search]")
        scrape_item.setup_as_profile(title)
        async with self.request_limiter:
            json_resp: dict[str, Any] = await self.client.get_json(self.domain, api_url, headers_inc=headers)

        posts: list[dict[str, Any]] = json_resp["posts"]
        hashtags: Generator[tuple[str, str]] = (("hash", hashtag["label"]) for hashtag in json_resp["hashtags"])
        users: Generator[tuple[str, str]] = (("user", user["username"]) for user in json_resp["users"])
        _ = await self.iter_posts(scrape_item, posts)
        for category, name in itertools.chain(hashtags, users):
            url = PRIMARY_BASE_DOMAIN / category / name
            new_scrape_item = scrape_item.create_child(url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, api_url: URL) -> None:
        headers = self.headers | {"Referer": str(scrape_item.url)}
        while True:
            async with self.request_limiter:
                json_resp: list[dict[str, Any]] = await self.client.get_json(self.domain, api_url, headers_inc=headers)

            last_post_id = await self.iter_posts(scrape_item, json_resp)
            if len(json_resp) < AMOUNT_LIMIT:
                break
            api_url = api_url.update_query(afterId=last_post_id)

    async def iter_posts(self, scrape_item: ScrapeItem, json_resp: list[dict[str, Any]]) -> str:
        for post_data in json_resp:
            post = Post(**post_data)
            new_scrape_item = scrape_item.create_child(post.page_url)
            await self.handle_post(new_scrape_item, post)
            scrape_item.add_children()
        return post.id

    async def handle_post(self, scrape_item: ScrapeItem, post: Post) -> None:
        scrape_item.url = post.page_url
        scrape_item.possible_datetime = post.timestamp
        title = self.create_title(f"{post.user} [user]", post.user_id)
        scrape_item.setup_as_album(title, album_id=post.user_id)
        filename, ext = self.get_filename_and_ext(f"{post.media_id}.mp4")
        custom_filename, _ = self.get_filename_and_ext(f"{post.label} [{post.id}].mp4")
        await self.handle_file(
            post.page_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=post.stream_url
        )
