from __future__ import annotations

import asyncio
import functools
import itertools
import re
from collections import defaultdict
from datetime import datetime  # noqa: TC003
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Concatenate, Literal, NamedTuple, NotRequired, ParamSpec

from pydantic import AliasChoices, BeforeValidator, Field
from typing_extensions import TypedDict  # Import from typing is not compatible with pydantic

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import NoExtensionError, ScrapeError
from cyberdrop_dl.models import AliasModel
from cyberdrop_dl.models.validators import falsy_as, falsy_as_none
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper, remove_parts

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Coroutine, Generator

    from aiohttp_client_cache.response import AnyResponse
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

    _P = ParamSpec("_P")


_DEFAULT_PAGE_SIZE = 50
_DISCORD_CHANNEL_PAGE_SIZE = 150
_POST_SELECTOR = "article.post-card a"
_find_http_urls = re.compile(r"(?:http(?!.*\.\.)[^ ]*?)(?=($|\n|\r\n|\r|\s|\"|\[/URL]|']\[|]\[|\[/img]|</|'))").finditer


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
    name: NotRequired[str]  # Sometimes present
    path: str
    server: NotRequired[str]  # Sometimes present in attachments


FileOrNone = Annotated[File | None, BeforeValidator(falsy_as_none)]
Tags = Annotated[list[str], BeforeValidator(lambda x: falsy_as(x, []))]


class Post(AliasModel):
    id: str
    content: str = ""
    file: FileOrNone = None
    attachments: list[File] = []  # noqa: RUF012
    published_or_added: datetime | None = Field(None, validation_alias=AliasChoices("published", "added"))
    date: int | None = None
    tags: Tags = []  # noqa: RUF012

    # `Any` to skip validation, but these are `yarl.URL`. We generate them internally so no validation is needed
    soup_attachments: list[Any] = []  # noqa: RUF012

    def model_post_init(self, *_) -> None:
        if self.published_or_added:
            self.date = to_timestamp(self.published_or_added)

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
    """A simplified version of Post that we can built from a soup, for sites that do not have an API.

    Cons: We need to make a request for every individual post"""

    title: str = ""
    content: str = ""
    user_name: str = ""
    date: str | None = None

    @staticmethod
    def from_soup(soup: BeautifulSoup) -> PartialUserPost:
        params = {}
        selectors = (PostSelectors.TITLE, PostSelectors.ALL_CONTENT, PostSelectors.USERNAME, PostSelectors.DATE)
        for name, selector in zip(PartialUserPost._fields, selectors, strict=True):
            if tag := soup.select_one(selector):
                params[name] = tag.get_text().strip()

        return PartialUserPost(**params)


def fallback_if_no_api(
    func: Callable[Concatenate[KemonoBaseCrawler, _P], Coroutine[None, None, None]],
) -> Callable[Concatenate[KemonoBaseCrawler, _P], Coroutine[None, None, None]]:
    """Calls a fallback method is the current instance does not define an API"""

    @functools.wraps(func)
    async def wrapper(self: KemonoBaseCrawler, *args: _P.args, **kwargs: _P.kwargs) -> None:
        if getattr(self, "API_ENTRYPOINT", None):
            return await func(self, *args, **kwargs)

        if fallback_func := getattr(self, f"{func.__name__}_w_no_api", None):
            return await fallback_func(*args, **kwargs)

        raise ValueError

    return wrapper


class KemonoBaseCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Model": "/<service>/user/<user_id>",
        "Favorites": (
            r"/favorites?type=post\|artist",
            r"/account/favorites/posts\|artists",
        ),
        "Search": "/search?q=...",
        "Individual Post": "/<service>/user/<user_id>/post/<post_id>",
        "Direct links": (
            "/data/...",
            "/thumbnail/...",
        ),
    }
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date} - {title}"
    API_ENTRYPOINT: ClassVar[AbsoluteHttpURL]
    SERVICES: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        Crawler._assert_fields_overrides(cls, "SERVICES")

    def __post_init__(self) -> None:
        self._user_names: dict[User, str] = {}
        self.__known_discord_servers: dict[str, DiscordServer] = {}
        self.__known_attachment_servers: dict[str, str] = {}
        self.__discord_servers_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.__ad_posts: list[str] = []

    @property
    def session_cookie(self) -> str:
        return ""

    @property
    def ignore_content(self) -> bool:
        return self.manager.config.ignore_options.ignore_coomer_post_content

    @property
    def ignore_ads(self) -> bool:
        return self.manager.config.ignore_options.ignore_coomer_ads

    async def async_startup(self) -> None:
        def check_kemono_page(response: AnyResponse) -> bool:
            if any(x in response.url.parts for x in self.SERVICES):
                return False
            if "discord/channel" in response.url.path:
                return False
            return True

        self.register_cache_filter(self.PRIMARY_URL, check_kemono_page)
        if getattr(self, "API_ENTRYPOINT", None):
            await self._get_usernames(self.API_ENTRYPOINT / "creators")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [service, "user", _, "post", _] if service in self.SERVICES:
                return await self.post(scrape_item)
            case [service, "user", _] if service in self.SERVICES:
                return await self.profile(scrape_item)
            case ["favorites"] if (type_ := scrape_item.url.query.get("type")) in ("post", "artist", None):
                type_ = type_ or "artist"
                return await self.favorites(scrape_item, type_)
            case ["account", "favorites", slug] if (type_ := slug.removesuffix("s")) in ("post", "artist"):
                return await self.favorites(scrape_item, type_)
            case ["posts"] if search_query := scrape_item.url.query.get("q"):
                return await self.search(scrape_item, search_query)
            case ["discord", "server", server_id]:
                return await self.discord_server(scrape_item, server_id)
            case ["discord", "server", _, channel_id]:
                return await self.discord_channel(scrape_item, channel_id)
            case ["thumbnail" | "thumbnails" | "data", _, *_]:
                return await self.handle_direct_link(scrape_item)
            case _:
                raise ValueError

    @fallback_if_no_api
    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        api_url = self.__make_api_url_w_offset(scrape_item.url, "posts")
        title = self.create_title(f"{query} [search]")
        scrape_item.setup_as_profile(title)
        await self.__iter_user_posts(scrape_item, api_url)

    @fallback_if_no_api
    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        path = (scrape_item.url / "posts").path
        api_url = self.__make_api_url_w_offset(scrape_item.url, path)
        scrape_item.setup_as_profile("")
        if self.ignore_ads:
            user = scrape_item.url.parts[3]
            self.log(f"[{self.FOLDER_DOMAIN}] filtering out all ad posts for {user}. This could take a while")
            await self.__iter_user_posts(scrape_item, api_url.update_query(q="#ad"))
        await self.__iter_user_posts(scrape_item, api_url)

    @fallback_if_no_api
    @error_handling_wrapper
    async def discord_server(self, scrape_item: ScrapeItem, server_id: str) -> None:
        scrape_item.setup_as_forum("")
        server = await self.__get_discord_server(server_id)
        for channel in server.channels:
            url = self.PRIMARY_URL / "discord/server" / server_id / channel.id
            new_scrape_item = scrape_item.create_child(url)
            self.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @fallback_if_no_api
    @error_handling_wrapper
    async def discord_channel(self, scrape_item: ScrapeItem, channel_id: str) -> None:
        scrape_item.setup_as_profile("")
        api_url = self.__make_api_url_w_offset(scrape_item.url, f"discord/channel/{channel_id}")
        async for posts in self._pager(api_url, step_size=_DISCORD_CHANNEL_PAGE_SIZE):
            if not isinstance(posts, list):
                error_msg = (
                    f"[{self.NAME}] Invalid API response for Discord channel '{channel_id}' posts (URL: {api_url}). "
                    f"Expected a list, but got type {type(posts).__name__}. "
                    f"Response data (truncated): {str(posts)[:200]}"
                )
                raise ScrapeError(422, error_msg)

            for post_data in posts:
                if not isinstance(post_data, dict):
                    error_msg = (
                        f"[{self.NAME}] Invalid post data type in list for "
                        f"Discord channel '{channel_id}' (URL template: {api_url}). "
                        f"Expected a dict for post data, but got type {type(post_data).__name__}. "
                        f"Post data (truncated): {str(post_data)[:200]}"
                    )
                    raise ScrapeError(422, error_msg)

                post = DiscordPost.model_validate(post_data)
                post_web_url = self.parse_url(post.web_path_qs)
                new_scrape_item = scrape_item.create_child(post_web_url)
                self.create_task(self._handle_discord_post_task(new_scrape_item, post))
                scrape_item.add_children()

            if len(posts) < _DISCORD_CHANNEL_PAGE_SIZE:
                break

    @fallback_if_no_api
    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        api_url = self.__make_api_url_w_offset(scrape_item.url)
        json_resp: dict[str, Any] = await self.__api_request(api_url)
        post = UserPost.model_validate(json_resp["post"])
        self._register_attachments_servers(json_resp["attachments"])
        self._handle_user_post(scrape_item, post)

    @fallback_if_no_api
    @error_handling_wrapper
    async def favorites(self, scrape_item: ScrapeItem, type_: Literal["post", "artist"]) -> None:
        if not self.session_cookie:
            msg = "No session cookie found in the config file, cannot scrape favorites"
            raise ScrapeError(401, msg)

        title = f"My favorite {type_}s"
        scrape_item.setup_as_profile(self.create_title(title))
        self.update_cookies({"session": self.session_cookie})
        query_url = (self.API_ENTRYPOINT / "account/favorites").with_query(type=type_)
        resp: list[dict[str, Any]] = await self.__api_request(query_url)
        self.update_cookies({"session": ""})

        for item in resp:
            url = self.PRIMARY_URL / item["service"] / "user" / (item.get("user") or ["name"])
            if type_ == "post":
                url = url / "post" / item["id"]

            new_scrape_item = scrape_item.create_child(url)
            self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None) -> None:
        scrape_item.url = _thumbnail_to_src(scrape_item.url)
        link = _thumbnail_to_src(url or scrape_item.url)
        hash_value = Path(link.name).stem
        if await self.check_complete_by_hash(link, "sha256", hash_value):
            return

        try:
            filename, ext = self.get_filename_and_ext(link.query.get("f") or link.name)
        except NoExtensionError:
            # Some patreon URLs have another URL as the filename:
            # ex: https://kemono.su/data/7a...27ad7e40bd.jpg?f=https://www.patreon.com/media-u/Z0F..00672794_
            filename, ext = self.get_filename_and_ext(link.name)

        await self.handle_file(link, scrape_item, link.name, ext, custom_filename=filename)

    # ~~~~~~~~ INTERNAL METHODS, not expected to be overridden, but could be ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _register_attachments_servers(self, attachments: list[File]) -> None:
        for attach in attachments:
            server = attach.get("server")
            if not server:
                continue

            path = attach["path"]
            if previous_server := self.__known_attachment_servers.get(path):
                if previous_server != server:
                    msg = (
                        f"[{self.NAME}] {path} found with multiple "  #
                        f"different servers: {server = } {previous_server = } "
                    )
                    self.log(msg, 30)
                continue
            self.__known_attachment_servers[path] = server

    def _handle_user_post(self, scrape_item: ScrapeItem, post: UserPost) -> None:
        user_name = self._user_names[post.user]
        title = self.create_title(user_name, post.user_id)
        scrape_item.setup_as_album(title, album_id=post.user_id)
        scrape_item.possible_datetime = post.date
        post_title = self.create_separate_post_title(post.title, post.id, post.date)
        scrape_item.add_to_parent_title(post_title)
        self.__handle_post(scrape_item, post)

    async def _handle_discord_post(self, scrape_item: ScrapeItem, post: DiscordPost) -> None:
        server = await self.__get_discord_server(post.server_id)
        title = self.create_title(f"{server.name} [discord]", server.id)
        channel_name = next(c.name for c in server.channels if c.id == post.channel_id)
        scrape_item.setup_as_album(title, album_id=server.id)
        scrape_item.possible_datetime = post.date
        scrape_item.add_to_parent_title(f"#{channel_name}")
        post_title = self.create_separate_post_title(None, post.id, post.date)
        scrape_item.add_to_parent_title(post_title)
        self.__handle_post(scrape_item, post)

    _handle_discord_post_task = auto_task_id(_handle_discord_post)

    def _handle_post_content(self, scrape_item: ScrapeItem, post: Post) -> None:
        """Gets links out of content in post and sends them to a new crawler."""
        if not post.content or self.ignore_content:
            return

        for link in self.__parse_content_urls(post):
            new_scrape_item = scrape_item.create_child(link)
            self.handle_external_links(new_scrape_item)
            scrape_item.add_children()

    @error_handling_wrapper
    async def _get_usernames(self, api_url: AbsoluteHttpURL) -> None:
        try:
            json_resp: list[dict[str, Any]] = await self.__api_request(api_url)
            self._user_names = {User(u["service"], u.get("user_id") or u["id"]): u["name"] for u in json_resp}
        except Exception as e:
            msg = f"Unable to get list of creators from {self.NAME}. Crawler has been disabled"
            self.disabled = True
            raise ScrapeError(503, msg) from e

    """~~~~~~~~  PRIVATE METHODS, should never be overridden ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def __parse_content_urls(self, post: Post) -> Generator[AbsoluteHttpURL]:
        seen: set[str] = set()
        for match in _find_http_urls(post.content):
            if (link := match.group().replace(".md.", ".")) not in seen:
                seen.add(link)
                try:
                    url = self.parse_url(link)
                except Exception:
                    pass
                else:
                    if self.DOMAIN not in url.host:
                        yield url

    def __has_ads(self, post: Post) -> bool:
        msg = f"[{self.FOLDER_DOMAIN}] skipping post #{post.id} (contains #advertisements)"
        if "#ad" in post.content or post.id in self.__ad_posts:
            self.log(msg)
            return True

        ci_tags = {tag.casefold() for tag in post.tags}
        if ci_tags.intersection({"ad", "#ad", "ads", "#ads"}):
            self.log(msg)
            return True

        return False

    def __handle_post(self, scrape_item: ScrapeItem, post: Post) -> None:
        if self.ignore_ads and self.__has_ads(post):
            return

        files = (self.__make_file_url(file) for file in post.all_files)

        seen: set[AbsoluteHttpURL] = set()
        for url in itertools.chain(files, post.soup_attachments):
            if url not in seen:
                seen.add(url)
                self.create_task(self.handle_direct_link(scrape_item, url))
                scrape_item.add_children()

        self._handle_post_content(scrape_item, post)

    def __make_file_url(self, file: File) -> AbsoluteHttpURL:
        path = file["path"]
        server = self.__known_attachment_servers.get(path) or ""
        url = self.parse_url(server + f"/data{path}")
        return url.with_query(f=file.get("name") or url.name)

    def __make_api_url_w_offset(self, web_url: AbsoluteHttpURL, path: str | None = None) -> AbsoluteHttpURL:
        api_url = self.API_ENTRYPOINT / (path or web_url.path).removeprefix("/")
        offset = int(web_url.query.get("o", 0))
        if query := web_url.query.get("q"):
            return api_url.update_query(o=offset, q=query)
        return api_url.update_query(o=offset)

    async def __get_discord_server(self, server_id: str) -> DiscordServer:
        """Get discord server information, making new API calls if needed."""
        async with self.__discord_servers_locks[server_id]:
            if server := self.__known_discord_servers.get(server_id):
                return server

            server_api_url = self.API_ENTRYPOINT / "discord/user" / server_id / "profile"
            server_profile: dict[str, Any] = await self.__api_request(server_api_url)
            name = server_profile.get("name") or f"Discord Server {server_id}"
            channels_api_url = self.API_ENTRYPOINT / "discord/channel/lookup" / server_id
            channels_resp: list[dict] = await self.__api_request(channels_api_url)
            channels = tuple(DiscordChannel(channel["name"], channel["id"]) for channel in channels_resp)
            self.__known_discord_servers[server_id] = server = DiscordServer(name, server_id, channels)
            return server

    async def __iter_user_posts(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL) -> None:
        filtering_ads = url.query.get("q") == "#ad"
        async for json_resp in self._pager(url):
            # From search results
            if isinstance(json_resp, dict):
                posts = json_resp.get("posts", [])

            # From profile
            elif isinstance(json_resp, list):
                posts: list[dict[str, Any]] = json_resp

            else:
                raise ScrapeError(422)

            if filtering_ads:
                self.__ad_posts.extend(p["id"] for p in posts)

            else:
                for post in (UserPost.model_validate(entry) for entry in posts):
                    post_web_url = self.parse_url(post.web_path_qs)
                    new_scrape_item = scrape_item.create_child(post_web_url)
                    if self.ignore_content or post.content:
                        self._handle_user_post(new_scrape_item, post)
                    elif self.ignore_ads and self.__has_ads(post):
                        continue
                    else:
                        self.create_task(self.run(new_scrape_item))
                    scrape_item.add_children()

            if len(posts) < _DEFAULT_PAGE_SIZE:
                break

    async def _pager(self, url: AbsoluteHttpURL, step_size: int | None = None) -> AsyncGenerator[Any]:
        """Yields JSON responses from API calls, or soup for web page calls, with configurable increments."""
        current_step_size = step_size or _DEFAULT_PAGE_SIZE
        init_offset = int(url.query.get("o") or 0)

        request = self.__api_request if "api" in url.parts else self.request_soup
        for current_offset in itertools.count(init_offset, current_step_size):
            yield await request(url.update_query(o=current_offset))

    async def __api_request(self, url: AbsoluteHttpURL) -> Any:
        """Get JSON from the API, with a custom Accept header."""

        # When using the 'text/css' header, the response is missing the charset header
        # and charset detection may return a random codec if the body has non english chars, so we force utf-8
        async with self.request(url, headers={"Accept": "text/css"}) as resp:
            return await resp.json(encoding="utf-8", content_type=False)

    # ~~~~~~~~~~ NO API METHODS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @error_handling_wrapper
    async def profile_w_no_api(self, scrape_item: ScrapeItem) -> None:
        scrape_item.setup_as_profile("")
        soup: BeautifulSoup
        async for soup in self._pager(scrape_item.url):
            n_posts = 0

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _POST_SELECTOR):
                n_posts += 1
                self.create_task(self.post_w_no_api_task(new_scrape_item))

            if n_posts < _DEFAULT_PAGE_SIZE:
                break

    @error_handling_wrapper
    async def post_w_no_api(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)
        service, _, user_id, _, post_id = scrape_item.url.parts[1:6]
        partial_post = PartialUserPost.from_soup(soup)
        if not partial_post.title or not partial_post.user_name:
            raise ScrapeError(422)

        def files():
            for selector in (
                PostSelectors.VIDEOS,
                PostSelectors.IMAGES,
                PostSelectors.ATTACHMENTS,
            ):
                for file in soup.select(selector):
                    yield self.parse_url(css.get_attr(file, "href"))

        post = UserPost(
            user_id=user_id,
            service=service,
            id=post_id,
            title=partial_post.title,
            content=partial_post.content,
            published_or_added=partial_post.date,  # type: ignore[reportArgumentType]
            soup_attachments=list(files()),
        )

        self._handle_user_post(scrape_item, post)

    post_w_no_api_task = auto_task_id(post_w_no_api)


class KemonoCrawler(KemonoBaseCrawler):
    SUPPORTED_PATHS: ClassVar = KemonoBaseCrawler.SUPPORTED_PATHS | {
        "Discord Server": "/discord/<server_id>",
        "Discord Server Channel": "/discord/server/<server_id>/<channel_id>#...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://kemono.cr")
    API_ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://kemono.cr/api/v1")
    DOMAIN: ClassVar[str] = "kemono"
    SERVICES: ClassVar[tuple[str, ...]] = (
        "afdian",
        "boosty",
        "dlsite",
        "fanbox",
        "fantia",
        "gumroad",
        "patreon",
        "subscribestar",
    )
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = "kemono.party", "kemono.su"

    @property
    def session_cookie(self):
        return self.manager.config_manager.authentication_data.kemono.session


def _thumbnail_to_src(og_url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    url = remove_parts(og_url, "thumbnails", "thumbnail").with_query(None)
    if name := og_url.query.get("f"):
        return url.with_query(f=name)
    return url
