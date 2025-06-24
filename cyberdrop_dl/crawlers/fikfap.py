from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import AliasPath, Field

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.models import AliasModel
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

API_ENTRYPOINT = AbsoluteHttpURL("https://api.fikfap.com")
PRIMARY_URL = AbsoluteHttpURL("https://fikfak.com")
POST_AMOUNT_LIMIT = 40  # Requesting more posts that this will return 400 - Bad Request


class Post(AliasModel):
    label: str
    id: str = Field(alias="postId", coerce_numbers_to_str=True)
    user_id: str = Field(alias="userId")
    media_id: str = Field(alias="mediaId")
    created_at: datetime = Field(alias="createdAt")
    stream_url: str = Field(alias="videoStreamUrl")
    user: str = Field(validation_alias=AliasPath("author", "username"))

    @property
    def url(self) -> AbsoluteHttpURL:
        return PRIMARY_URL / "posts" / self.id


class FikFapCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Post": "/post/...",
        "User": "/user/...",
        "hashtag": "/hash/...",
        "Search": "/search?q=...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "fikfap"
    FOLDER_DOMAIN: ClassVar[str] = "FikFap"

    def __post_init__(self) -> None:
        self.id_token = ""
        origin = str(PRIMARY_URL)
        self.headers = {"Referer": origin, "Origin": origin, "Authorization-Anonymous": self.id_token}

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
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
        canonical_url = PRIMARY_URL / "posts" / post_id
        if await self.check_complete_from_referer(canonical_url):
            return
        json_resp: dict[str, Any] = await self._make_api_request(scrape_item, API_ENTRYPOINT / "posts" / post_id)
        await self.handle_post(scrape_item, Post.model_validate(json_resp))

    async def user(self, scrape_item: ScrapeItem) -> None:
        user_name = scrape_item.url.name
        scrape_item.setup_as_profile("")
        await self.collection(
            scrape_item,
            API_ENTRYPOINT.joinpath("profile/username", user_name, "posts").with_query(amount=POST_AMOUNT_LIMIT),
        )

    async def hashtag(self, scrape_item: ScrapeItem) -> None:
        label = scrape_item.url.name
        scrape_item.setup_as_album(self.create_title(f"{label} [hashtag]"))
        await self.collection(
            scrape_item,
            API_ENTRYPOINT.joinpath("hashtags/label", label, "posts").with_query(
                amount=POST_AMOUNT_LIMIT, topPercentage=33
            ),
        )

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        search_query = scrape_item.url.query["q"]
        scrape_item.setup_as_profile(self.create_title(f"{search_query} [search]"))
        json_resp: dict[str, list[dict[str, Any]]] = await self._make_api_request(
            scrape_item, API_ENTRYPOINT.joinpath("search").with_query(q=search_query, amount=POST_AMOUNT_LIMIT)
        )
        for post in (Post.model_validate(data) for data in json_resp["posts"]):
            await self._proccess_post(scrape_item, post)
        for hashtag in json_resp["hashtags"]:
            self._proccess_result(scrape_item, PRIMARY_URL / "hash" / hashtag["label"])
        for user in json_resp["users"]:
            self._proccess_result(scrape_item, PRIMARY_URL / "user" / user["username"])

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, api_url: AbsoluteHttpURL) -> None:
        last_post_id: str = ""
        while True:
            json_resp: list[dict[str, Any]] = await self._make_api_request(scrape_item, api_url)
            for post in (Post.model_validate(data) for data in json_resp):
                await self._proccess_post(scrape_item, post)
                last_post_id = post.id

            if len(json_resp) < POST_AMOUNT_LIMIT:
                break
            api_url = api_url.update_query(afterId=last_post_id)

    def _proccess_result(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL) -> None:
        new_scrape_item = scrape_item.create_child(url)
        self.manager.task_group.create_task(self.run(new_scrape_item))
        scrape_item.add_children()

    async def _proccess_post(self, scrape_item: ScrapeItem, post: Post) -> None:
        new_scrape_item = scrape_item.create_child(post.url)
        await self.handle_post(new_scrape_item, post)
        scrape_item.add_children()

    async def _make_api_request(self, scrape_item: ScrapeItem, api_url: AbsoluteHttpURL) -> Any:
        headers = self.headers | {"Referer": str(scrape_item.url)}
        async with self.request_limiter:
            return await self.client.get_json(self.DOMAIN, api_url, headers)

    async def handle_post(self, scrape_item: ScrapeItem, post: Post) -> None:
        m3u8_playlist_url = self.parse_url(post.stream_url)
        m3u8_media, rendition_group = await self.get_m3u8_playlist(m3u8_playlist_url)

        scrape_item.url = post.url
        scrape_item.possible_datetime = to_timestamp(post.created_at)
        scrape_item.setup_as_album(self.create_title(f"{post.user} [user]", post.user_id), album_id=post.user_id)
        filename, ext = self.get_filename_and_ext(f"{post.media_id}.mp4")
        custom_filename = self.create_custom_filename(
            post.label, ext, file_id=post.id, resolution=rendition_group.resolution.name
        )

        await self.handle_file(
            post.url,
            scrape_item,
            filename,
            ext,
            custom_filename=custom_filename,
            debrid_link=m3u8_playlist_url,
            m3u8_media=m3u8_media,
        )
