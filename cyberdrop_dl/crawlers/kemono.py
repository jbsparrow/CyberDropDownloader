from __future__ import annotations

import asyncio
import calendar
import functools
import itertools
import re
from collections import defaultdict
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Annotated, Any, NamedTuple, NotRequired, cast

from pydantic import AliasChoices, BeforeValidator, Field
from typing_extensions import TypedDict  # Import from typing is not compatible with pydantic
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import NoExtensionError, ScrapeError
from cyberdrop_dl.types import AliasModel
from cyberdrop_dl.utils.utilities import error_handling_wrapper, remove_parts
from cyberdrop_dl.utils.validators import parse_falsy_as_none

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Coroutine, Generator

    from aiohttp_client_cache.response import AnyResponse
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

MAX_OFFSET_PER_CALL = 50
LINK_REGEX = re.compile(r"(?:http(?!.*\.\.)[^ ]*?)(?=($|\n|\r\n|\r|\s|\"|\[/URL]|']\[|]\[|\[/img]|</|'))")
POST_SELECTOR = "article.post-card a"
DISCORD_SERVER_NAME_SELECTOR = "spam[class*=__profile-image] + span[itemprop='name']"


class PostSelectors:
    FILES = "div[class*=__files]"
    CONTENT = "div[class*=__content]"
    ATTACHMENTS = "a[class*=__attachment-link]"
    IMAGES = "div[class=fileThumb]"
    VIDEOS = "video[class*=__video] source"
    ALL_CONTENT = f"{FILES}, {CONTENT}"

    DATE_PUBLISHED = "div[class*=__published] time[class=timestamp]"
    DATE_ADDED = "div[class*=__added]"
    DATE = f"{DATE_PUBLISHED}, {DATE_ADDED}"

    TITLE = "h1[class*=__title]"
    USERNAME = "a[class*=__user-name]"


_POST = PostSelectors()


class UserURL(NamedTuple):
    # format: https://kemono.su/<service>/user/<user_id>/post/<post_id>
    # ex: https://kemono.su/patreon/user/92916478/post/87864845
    service: str
    user_id: str
    post_id: str | None = None

    @staticmethod
    def parse(url: URL) -> UserURL:
        if n_parts := len(url.parts) > 3:
            post_id = url.parts[5] if n_parts > 5 else None
            return UserURL(url.parts[1], url.parts[3], post_id)
        msg = "Invalid user URL"
        raise ValueError(msg)


class UserPostURL(UserURL):
    post_id: str

    @staticmethod
    def parse(url: URL) -> UserPostURL:
        result = UserURL.parse(url)
        assert result.post_id, "Individual posts must have a post_id"
        return cast("UserPostURL", result)


class DiscordURL(NamedTuple):
    # format: https://kemono.su/discord/server/<server_id>/<channel_id>
    # ex: https://kemono.su/discord/server/891670433978531850/892624523034255371
    server_id: str
    channel_id: str | None = None  # Only present for individual channels URLs

    @staticmethod
    def parse(url: URL) -> DiscordURL:
        return DiscordURL(*url.parts[3:5])


class DiscordChannel(NamedTuple):
    name: str
    id: str


class DiscordServer(NamedTuple):
    name: str
    id: str
    channels: tuple[DiscordChannel, ...]


class User(NamedTuple):
    service: str
    id: str


class File(TypedDict):
    name: str
    path: str
    server: NotRequired[str]  # Sometimes present in attachments


FileOrNone = Annotated[File | None, BeforeValidator(parse_falsy_as_none)]


class Post(AliasModel):
    id: str
    content: str = ""
    file: FileOrNone = None
    attachments: list[File] = []  # noqa: RUF012
    published_or_added: datetime | None = Field(None, validation_alias=AliasChoices("published", "added"))
    soup_attachments: list[Any] = []  # noqa: RUF012, `Any` to skip validation, but these are `yarl.URL`. We generate them internally so no validation is needed
    date: int | None = None

    def model_post_init(self, *_) -> None:
        if self.published_or_added:
            self.date = calendar.timegm(self.published_or_added.timetuple())

    @property
    def all_files(self) -> Generator[File]:
        if self.file:
            yield self.file
        yield from self.attachments


class UserPost(Post):
    service: str
    user_id: str = Field(validation_alias="user")
    title: str

    @property
    def user(self) -> User:
        return User(self.service, self.user_id)

    @property
    def web_path_qs(self) -> str:
        return f"{self.service}/user/{self.user_id}/post/{self.id}"


class DiscordPost(Post):
    server_id: str = Field(validation_alias="server")
    channel_id: str = Field(validation_alias="channel")

    @property
    def web_path_qs(self) -> str:
        return f"discord/server/{self.server_id}/{self.channel_id}#{self.id}"


class PartialUserPost(NamedTuple):
    """A simplified version of Post that we can built from a soup, for sites that do not have an API

    Pros: We can get the post data + user_name in a single request

    Cons: We need to make a request for every individual post"""

    title: str = ""
    content: str = ""
    user_name: str = ""
    date: str | None = None

    @staticmethod
    def from_soup(soup: BeautifulSoup) -> PartialUserPost:
        info = {}
        names = "title", "content", "user_name", "date"
        selectors = (_POST.TITLE, _POST.ALL_CONTENT, _POST.USERNAME, _POST.DATE)
        for name, selector in zip(names, selectors, strict=True):
            if tag := soup.select_one(selector):
                info[name] = tag.text.strip()

        return PartialUserPost(**info)


def fallback_if_no_api(func: Callable[..., Coroutine[None, None, Any]]) -> Callable[..., Coroutine[None, None, Any]]:
    """Calls a fallback method is the current instance does not define an API"""

    @functools.wraps(func)
    async def wrapper(self: KemonoCrawler, *args, **kwargs) -> Any:
        if self.api_entrypoint:
            return await func(self, *args, **kwargs)
        fallback_func = getattr(self, f"{func.__name__}_w_no_api", None)
        if not fallback_func:
            raise ValueError
        return await fallback_func(self, *args, **kwargs)

    return wrapper


class KemonoCrawler(Crawler):
    primary_base_domain = URL("https://kemono.su")
    DEFAULT_POST_TITLE_FORMAT = "{date} - {title}"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "kemono", "Kemono")
        self.api_entrypoint: URL = URL("https://kemono.su/api/v1")
        self.__known_user_names: dict[User, str] = {}
        self.__known_discord_servers: dict[str, DiscordServer] = {}
        self.__known_attachment_servers: dict[str, str] = {}
        self.__user_names_locks: dict[User, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.__discord_servers_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.services: tuple[str, ...] = (
            "afdian",
            "boosty",
            "dlsite",
            "fanbox",
            "fantia",
            "gumroad",
            "patreon",
            "subscribestar",
        )
        self.session_cookie = self.manager.config_manager.authentication_data.kemono.session

    async def async_startup(self) -> None:
        def check_kemono_page(response: AnyResponse) -> bool:
            if any(x in response.url.parts for x in self.services):
                return False
            if "discord/channel" in response.url.path:
                return False
            return True

        self.register_cache_filter(self.primary_base_domain, check_kemono_page)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "discord" in scrape_item.url.parts:
            return await self.discord(scrape_item)
        return await self._fetch_kemono_defaults(scrape_item)

    async def _fetch_kemono_defaults(self, scrape_item: ScrapeItem) -> None:
        """Helper fetch method for subclasses.

        Subclasses can override the normal `fetch` method to add their own custom filters and them call this method at the end

        Super().fetch MUST NOT be used, otherwise a new task_id will be created"""
        if "thumbnails" in scrape_item.url.parts:
            return await self.handle_direct_link(scrape_item)
        if "post" in scrape_item.url.parts:
            return await self.post(scrape_item)
        if scrape_item.url.name == "posts":
            if not scrape_item.url.query.get("q"):
                raise ValueError
            return await self.search(scrape_item)
        if any(x in scrape_item.url.parts for x in self.services):
            return await self.profile(scrape_item)
        if "favorites" in scrape_item.url.parts:
            return await self.favorites(scrape_item)
        await self.handle_direct_link(scrape_item)

    @fallback_if_no_api
    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        """Scrapes results from a search query."""
        query = scrape_item.url.query["q"]
        api_url = self.__make_api_url_w_offset("posts", scrape_item.url)
        title = self.create_title(f"{query} [search]")
        scrape_item.setup_as_profile(title)
        await self.__iter_user_posts_from_url(scrape_item, api_url)

    @fallback_if_no_api
    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        url_info = UserURL.parse(scrape_item.url)
        path = f"{url_info.service}/user/{url_info.user_id}"
        api_url = self.__make_api_url_w_offset(path, scrape_item.url)
        scrape_item.setup_as_profile("")
        await self.__iter_user_posts_from_url(scrape_item, api_url)

    @fallback_if_no_api
    @error_handling_wrapper
    async def discord(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a discord server or channel."""
        discord = DiscordURL.parse(scrape_item.url)
        if discord.channel_id:
            return await self.discord_channel(scrape_item, discord.channel_id)

        await self.discord_server(scrape_item, discord.server_id)

    async def discord_server(self, scrape_item: ScrapeItem, server_id: str) -> None:
        scrape_item.setup_as_forum("")
        server = await self.__get_discord_server(server_id)
        for channel in server.channels:
            url = self.primary_base_domain / "discord/server" / server_id / channel.id
            new_scrape_item = scrape_item.create_child(url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    async def discord_channel(self, scrape_item: ScrapeItem, channel_id: str) -> None:
        scrape_item.setup_as_profile("")
        api_url = self.__make_api_url_w_offset(f"discord/channel/{channel_id}", scrape_item.url)
        async for json_resp in self.__api_pager(api_url):
            n_posts = 0
            for post in (DiscordPost(**entry) for entry in json_resp):  # type: ignore
                n_posts += 1
                link = self.parse_url(post.web_path_qs)
                new_scrape_item = scrape_item.create_child(link)
                await self._handle_discord_post(new_scrape_item, post)
                scrape_item.add_children()

            if not n_posts < MAX_OFFSET_PER_CALL:
                break

    @fallback_if_no_api
    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user post."""
        url_info = UserPostURL.parse(scrape_item.url)
        path = f"{url_info.service}/user/{url_info.user_id}/post/{url_info.post_id}"
        api_url = self.__make_api_url_w_offset(path, scrape_item.url)
        async with self.request_limiter:
            json_resp: dict[str, dict] = await self.client.get_json(self.domain, api_url)

        post = UserPost(**json_resp["post"])
        self._register_attachments_servers(json_resp["attachments"])  # type: ignore
        await self._handle_user_post(scrape_item, post)

    def _register_attachments_servers(self, attachments: list[File]) -> None:
        for attach in attachments:
            if server := attach.get("server"):
                path = attach["path"]
                if previous_server := self.__known_attachment_servers.get(path):
                    if previous_server != server:
                        msg = f"[{self.name}] {path} found with multiple diferent servers: {server = } {previous_server = } "
                        self.log_debug(msg)
                    continue
                self.__known_attachment_servers[path] = server

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None) -> None:
        """Handles a direct link."""

        def clean_url(og_url: URL) -> URL:
            if "thumbnails" in og_url.parts:
                return remove_parts(og_url, "thumbnails")
            return og_url

        scrape_item.url = clean_url(scrape_item.url)
        link = clean_url(url or scrape_item.url)
        try:
            filename, ext = self.get_filename_and_ext(link.query.get("f") or link.name)
        except NoExtensionError:
            # Some patreon URLs have another URL as the filename: https://kemono.su/data/7a...27ad7e40bd.jpg?f=https://www.patreon.com/media-u/Z0F..00672794_
            filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def favorites(self, scrape_item: ScrapeItem) -> None:
        """Scrapes the user's favorite artists or posts and enqueues them for processing."""
        if not self.session_cookie:
            raise ScrapeError(401, "No session cookie found in the config file, cannot scrape favorites")

        is_post = scrape_item.url.query.get("type") == "post"
        title = "My favorite posts" if is_post else "My favorite artists"
        scrape_item.setup_as_profile(self.create_title(title))

        self.update_cookies({"session": self.session_cookie})
        api_url = self.api_entrypoint / "account/favorites"
        query_url = api_url.with_query(type="post" if is_post else "artist")

        async with self.request_limiter:
            json_resp: list[dict] = await self.client.get_json(self.domain, query_url)

        self.update_cookies({"session": ""})

        for item in json_resp:
            if is_post:
                post_id, user_id, service = item["id"], item["user"], item["service"]
                url = self.primary_base_domain / service / "user" / user_id / "post" / post_id
            else:
                user_id, service = item["id"], item["service"]
                url = self.primary_base_domain / service / "user" / user_id

            new_scrape_item = scrape_item.create_child(url)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    # ~~~~~~~~ INTERNAL METHODS, not expected to be overriden, but could be ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    async def _handle_user_post(self, scrape_item: ScrapeItem, post: UserPost):
        user_name = await self.__get_user_name(post.user)
        title = self.create_title(user_name, post.user_id)
        scrape_item.setup_as_album(title, album_id=post.user_id)
        scrape_item.possible_datetime = post.date
        post_title = self.create_separate_post_title(post.title, post.id, post.date)
        scrape_item.add_to_parent_title(post_title)

        await self.__handle_post(scrape_item, post)

    async def _handle_discord_post(self, scrape_item: ScrapeItem, post: DiscordPost):
        server = await self.__get_discord_server(post.server_id)
        title = self.create_title(f"{server.name} [discord]", server.id)
        channel_name = next(c.name for c in server.channels if c.id == post.channel_id)
        scrape_item.setup_as_album(title, album_id=server.id)
        scrape_item.possible_datetime = post.date
        scrape_item.add_to_parent_title(f"#{channel_name}")

        post_title = self.create_separate_post_title(None, post.id, post.date)
        scrape_item.add_to_parent_title(post_title)

        await self.__handle_post(scrape_item, post)

    def _handle_post_content(self, scrape_item: ScrapeItem, post: Post) -> None:
        """Gets links out of content in post ans sends them to a new crawler."""
        if not post.content:
            return

        def gen_yarl_urls():
            for match in re.finditer(LINK_REGEX, post.content):
                link = match.group().replace(".md.", ".")
                try:
                    url = self.parse_url(link)
                    yield url
                except ValueError:
                    pass

        for link in gen_yarl_urls():
            if not link.host or self.domain in link.host:
                continue
            new_scrape_item = scrape_item.create_child(link)
            self.handle_external_links(new_scrape_item)
            scrape_item.add_children()

    async def _register_user_name(self, user: User, user_name: str) -> None:
        """Save the user_name to the internal dict

        NOTE: This should never be overriden.
        It's defined as internal to allow subclasses to override `post_w_no_api` and still be able to modify the private self.__known_user_names
        """

        async with self.__user_names_locks[user]:
            if self.__known_user_names.get(user):
                return
            self.__known_user_names[user] = user_name

    """~~~~~~~~  PRIVATE METHODS, should never be overriden ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def __handle_post(self, scrape_item: ScrapeItem, post: Post):
        # Process files if the post was generated from an API call
        for file in post.all_files:
            file_url = self.__make_file_url(file)
            await self.handle_direct_link(scrape_item, file_url)
            scrape_item.add_children()

        # Process files if the post was generated from soup
        for file_url in post.soup_attachments:
            await self.handle_direct_link(scrape_item, file_url)
            scrape_item.add_children()

        self._handle_post_content(scrape_item, post)

    def __make_file_url(self, file: File) -> URL:
        server = self.__known_attachment_servers.get(file["path"], "")
        url = server + f"/data{file['path']}"
        return self.parse_url(url).with_query(f=file["name"])

    def __make_api_url_w_offset(self, path: str, og_url: URL) -> URL:
        api_url = self.api_entrypoint / path
        offset = int(og_url.query.get("o", 0))
        if query := og_url.query.get("q"):
            return api_url.update_query(o=offset, q=query)
        return api_url.update_query(o=offset)

    async def __get_user_name(self, user: User) -> str:
        """Gets the user name, making a new API call if needed"""
        async with self.__user_names_locks[user]:
            if user_name := self.__known_user_names.get(user):
                return user_name

            api_url = self.api_entrypoint / user.service / "user" / user.id / "posts-legacy"
            async with self.request_limiter:
                profile_json: dict = await self.client.get_json(self.domain, api_url)

            self.__known_user_names[user] = user_name = profile_json["props"]["name"]
            return user_name

    async def __get_discord_server(self, server_id: str) -> DiscordServer:
        """Get discord server information, making a new api call if needed"""
        async with self.__discord_servers_locks[server_id]:
            if server := self.__known_discord_servers.get(server_id):
                return server

            url = self.primary_base_domain / "discord/user" / server_id / "links"
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, url)

            name = soup.select_one(DISCORD_SERVER_NAME_SELECTOR).text  # type: ignore
            url = self.api_entrypoint / "discord/channel/lookup" / server_id
            async with self.request_limiter:
                json_resp: list[dict] = await self.client.get_json(self.domain, url)

            channels = tuple(DiscordChannel(channel["name"], channel["id"]) for channel in json_resp)
            self.__known_discord_servers[server_id] = server = DiscordServer(name, server_id, channels)
            return server

    async def __iter_user_posts_from_url(self, scrape_item: ScrapeItem, url: URL) -> None:
        async for json_resp in self.__api_pager(url):
            n_posts = 0

            # From search results
            if isinstance(json_resp, dict):
                posts = json_resp.get("posts")  # type: ignore
            # From profile
            elif isinstance(json_resp, list):
                posts: list[dict[str, Any]] = json_resp
            else:
                raise ScrapeError(422)

            if not posts:
                return

            for post in (UserPost(**entry) for entry in posts):
                n_posts += 1
                link = self.parse_url(post.web_path_qs)
                new_scrape_item = scrape_item.create_child(link)
                await self._handle_user_post(new_scrape_item, post)
                scrape_item.add_children()

            if not n_posts < MAX_OFFSET_PER_CALL:
                break

    async def __api_pager(self, url: URL) -> AsyncGenerator[dict[str, Any]]:
        """Yields jsons response from api calls, with increments of `MAX_OFFSET_PER_CALL`"""
        init_offset = int(url.query.get("o") or 0)
        for offset in itertools.count(init_offset, MAX_OFFSET_PER_CALL):
            api_url = url.update_query(o=offset)
            async with self.request_limiter:
                json_resp: dict = await self.client.get_json(self.domain, api_url)
            yield json_resp

    # ~~~~~~~~~~ NO API METHODS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    async def discord_w_no_api(self, scrape_item: ScrapeItem) -> Any:
        raise NotImplementedError

    async def search_w_no_api(self, scrape_item: ScrapeItem) -> Any:
        raise NotImplementedError

    @error_handling_wrapper
    async def profile_w_no_api(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        url_info = UserURL.parse(scrape_item.url)
        path = f"{url_info.service}/user/{url_info.user_id}"
        api_url = self.primary_base_domain / path
        scrape_item.setup_as_profile("")
        init_offset = int(scrape_item.url.query.get("o") or 0)
        for offset in itertools.count(init_offset, MAX_OFFSET_PER_CALL):
            n_posts = 0
            api_url = api_url.with_query(o=offset)
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, api_url)

            for post in soup.select(POST_SELECTOR):
                n_posts += 1
                link = self.parse_url(post["href"])  # type: ignore
                new_scrape_item = scrape_item.create_child(link)
                await self.post_w_no_api(new_scrape_item)
                scrape_item.add_children()

            if n_posts < MAX_OFFSET_PER_CALL:
                break

    @error_handling_wrapper
    async def post_w_no_api(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user post."""

        url_info = UserPostURL.parse(scrape_item.url)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        post = PartialUserPost.from_soup(soup)
        if not post.title or not post.user_name:
            raise ScrapeError(422)

        files: list[URL] = []
        for selector in (_POST.VIDEOS, _POST.IMAGES, _POST.ATTACHMENTS):
            for file in soup.select(selector):
                files.append(self.parse_url(file["href"]))  # type: ignore

        full_post = UserPost(
            user_id=url_info.user_id,
            service=url_info.service,
            id=url_info.post_id,
            title=post.title,
            content=post.content,
            published_or_added=post.date,  # type: ignore
            soup_attachments=files,
        )

        await self._register_user_name(full_post.user, post.user_name)
        await self._handle_user_post(scrape_item, full_post)
