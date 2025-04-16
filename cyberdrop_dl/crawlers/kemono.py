from __future__ import annotations

import calendar
import functools
import itertools
import re
from typing import TYPE_CHECKING, Any, NamedTuple, TypedDict

from pydantic import AliasChoices, Field
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError, ScrapeError
from cyberdrop_dl.config_definitions.custom.types import AliasModel
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, remove_parts

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
    from datetime import datetime

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

LINK_REGEX = re.compile(r"(?:http(?!.*\.\.)[^ ]*?)(?=($|\n|\r\n|\r|\s|\"|\[/URL]|']\[|]\[|\[/img]|</|'))")


POST_SELECTOR = "article.post-card a"


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


class URLInfo(NamedTuple):
    service: str = "Unknown"
    _user: str = ""  # the literal word "user" in the URL ex: "/user/"
    user: str = "Unknown"
    _post: str = ""  # the literal word "post" in the URL ex: "/post/"
    post_id: str = "Unknown"

    @staticmethod
    def parse(url: URL) -> URLInfo:
        return URLInfo(*url.parts[1:6])


class UserInfo(NamedTuple):
    # Same information as URLInfo but includes the user_name.
    # Getting the user_name requires making a new request when using the API
    service: str
    user: str
    post_id: str | None
    user_name: str  # The is the proper name, capitalized


class File(TypedDict):
    name: str
    path: str


class Post(AliasModel):
    user: str
    user_name: str  # The is the proper name, capitalized
    id: str
    title: str
    file: File | None = None  # TODO: Verify is a post can have more that 1 file
    content: str = ""
    attachments: list[File] = []  # noqa: RUF012
    _published: datetime | None = Field(None, validation_alias=AliasChoices("published", "added"))
    soup_attachments: list[URL] = []  # noqa: RUF012

    def model_post_init(self):
        if self._published:
            self.date = calendar.timegm(self._published.timetuple())
        else:
            self.date: int | None = None

    @property
    def all_files(self) -> Generator[File]:
        if self.file:
            yield self.file
        yield from self.attachments


class PartialPost(NamedTuple):
    """A simplified version of Post that we can built from a soup, for sites that do not have an API"""

    title: str = ""
    content: str = ""
    user_name: str = ""  # The is the proper name, capitalized
    date: str | None = None

    @staticmethod
    def from_soup(soup: BeautifulSoup) -> PartialPost:
        info = {}
        names = "title", "content", "user_name", "date"
        selectors = (_POST.TITLE, _POST.ALL_CONTENT, _POST.USERNAME, _POST.DATE)
        for name, selector in zip(names, selectors, strict=True):
            if tag := soup.select_one(selector):
                info[name] = tag.text.strip()

        return PartialPost(**info)


def fallback_if_no_api(func: Callable[..., Coroutine[None, None, Any]]) -> Callable[..., Coroutine[None, None, Any]]:
    """Calls a fallback method is the current instance does not define an API"""

    @functools.wraps(func)
    async def wrapper(self: KemonoCrawler, *args, **kwargs):
        if self.api_entrypoint:
            return await func(self, *args, **kwargs)
        fallback_func = getattr(self, f"{func.__name__}_w_no_api", None)
        if not fallback_func:
            raise ScrapeError(422)
        return await fallback_func(self, *args, **kwargs)

    return wrapper


class KemonoCrawler(Crawler):
    primary_base_domain = URL("https://kemono.su")
    DEFAULT_POST_TITLE_FORMAT = "{date} - {title}"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "kemono", "Kemono")
        self.api_entrypoint: URL = URL("https://kemono.su/api/v1")
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

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        return await self._fetch_kemono_defaults(scrape_item)

    async def _fetch_kemono_defaults(self, scrape_item: ScrapeItem) -> None:
        """Helper fetch method for subclasses.

        Subclasses can override the normal `fetch` method to add their own custom filters and them call this method at the end

        Super().fetch MUST NOT be used, otherwise a new task_id will be created"""
        if "thumbnails" in scrape_item.url.parts:
            scrape_item.url = remove_parts(scrape_item.url, "thumbnails")
            return await self.handle_direct_link(scrape_item)
        if "discord" in scrape_item.url.parts:
            return await self.discord(scrape_item)
        if "post" in scrape_item.url.parts:
            return await self.post(scrape_item)
        if scrape_item.url.name == "posts" and scrape_item.url.query.get("q"):
            return await self.search(scrape_item)
        if any(x in scrape_item.url.parts for x in self.services):
            return await self.profile(scrape_item)
        await self.handle_direct_link(scrape_item)

    @error_handling_wrapper
    @fallback_if_no_api
    async def search(self, scrape_item: ScrapeItem) -> None:
        """Scrapes results from a search query."""
        query, api_url = self._api_w_offset("posts", scrape_item.url)
        title = self.create_title(f"Search - {query}")
        scrape_item.setup_as_album(title)
        await self.iter_from_url(scrape_item, api_url)

    @error_handling_wrapper
    @fallback_if_no_api
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        info = await self.get_user_info(scrape_item)
        _, api_url = self._api_w_offset(f"{info.service}/user/{info.user}", scrape_item.url)
        await self.iter_from_url(scrape_item, api_url)

    @error_handling_wrapper
    @fallback_if_no_api
    async def discord(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        channel = scrape_item.url.raw_fragment
        _, api_url = self._api_w_offset(f"discord/channel/{channel}", scrape_item.url)
        await self.iter_from_url(scrape_item, api_url)

    @error_handling_wrapper
    @fallback_if_no_api
    async def post(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a post."""
        user_info = await self.get_user_info(scrape_item)
        assert user_info.post_id
        path = f"{user_info.service}/user/{user_info.user}/post/{user_info.post_id}"
        _, api_url = self._api_w_offset(path, scrape_item.url)
        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.domain, api_url)

        post = Post(**json_resp["post"])
        await self._handle_post(scrape_item, post)

    async def iter_from_url(self, scrape_item: ScrapeItem, url: URL):
        async for json_resp in self.api_pager(url):
            posts: list[dict[str, Any]] = json_resp.get("posts", [])
            if not posts:
                if "attachments" not in json_resp:
                    posts = json_resp  # type: ignore
                else:
                    continue

            for post in (Post(**entry) for entry in posts):
                await self._handle_post(scrape_item, post)

    async def api_pager(self, url: URL) -> AsyncGenerator[dict[str, Any]]:
        offset = int(url.query.get("o") or 0)
        while True:
            api_url = url.update_query(o=offset)
            async with self.request_limiter:
                json_resp: dict = await self.client.get_json(self.domain, api_url)
            yield json_resp
            if not json_resp:
                break
            # TODO: Check whats the maximun offset we can user
            # TODO: Verify if must use different max offsets for each url type / service
            offset += 50

    async def _handle_post(self, scrape_item: ScrapeItem, post: Post):
        scrape_item.setup_as_album(post.title, album_id=post.id)
        scrape_item.possible_datetime = post.date
        post_title = self.create_separate_post_title(post.title, post.id, post.date)
        scrape_item.add_to_parent_title(post_title)

        # Process files if the post was generated from an API call
        for file in post.all_files:
            file_url = self._make_file_url(file)
            await self.handle_direct_link(scrape_item, file_url)
            scrape_item.add_children()

        # Process files if the posts was generated from soup
        for file_url in post.soup_attachments:
            await self.handle_direct_link(scrape_item, file_url)
            scrape_item.add_children()

        self._handle_post_content(scrape_item, post)

    def _make_file_url(self, file: File) -> URL:
        return self.parse_url(f"/data/{file['path']}").with_query(f=file["name"])

    def _api_w_offset(self, path: str, og_url: URL) -> tuple[str, URL]:
        api_url = self.api_entrypoint / path
        offset = int(og_url.query.get("o", 0))
        if query := og_url.query.get("q"):
            return query, api_url.update_query(o=offset, q=query)
        return "", api_url.update_query(o=offset)

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

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None) -> None:
        """Handles a direct link."""
        link = url or scrape_item.url
        try:
            filename, ext = self.get_filename_and_ext(link.query.get("f") or link.name)
        except NoExtensionError:
            # Some patreon URLs have another URL as the filename: https://kemono.su/data/7a...27ad7e40bd.jpg?f=https://www.patreon.com/media-u/Z0F..00672794_
            filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_user_info(self, scrape_item: ScrapeItem) -> UserInfo:
        """Gets the user info, making a new API call"""
        url_info = URLInfo.parse(scrape_item.url)
        api_url = self.api_entrypoint / url_info.service / "user" / url_info.user / "posts-legacy"
        async with self.request_limiter:
            profile_json, _ = await self.client.get_json(self.domain, api_url, cache_disabled=True)

        properties: dict[str, str] = profile_json.get("props", {})
        user_name = properties.get("name", url_info.user)
        return UserInfo(url_info.service, url_info.user, url_info.post_id, user_name)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    async def discord_w_no_api(self, scrape_item: ScrapeItem):
        raise NotImplementedError

    async def search_w_no_api(self, scrape_item: ScrapeItem):
        raise NotImplementedError

    @error_handling_wrapper
    async def profile_w_no_api(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        url_info = URLInfo.parse(scrape_item.url)
        api_url = self.primary_base_domain / url_info.service / "user" / url_info.user
        scrape_item.setup_as_profile("")

        for offset in itertools.count(0, 50):
            api_url = api_url.with_query(o=offset)
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, api_url)

            for post in soup.select(POST_SELECTOR):
                post_link = self.parse_url(post["href"])  # type: ignore
                new_scrape_item = scrape_item.create_child(post_link)
                await self.post_w_no_api(new_scrape_item)
                scrape_item.add_children()

    @error_handling_wrapper
    async def post_w_no_api(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a post."""

        url_info = URLInfo.parse(scrape_item.url)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        post_info = PartialPost.from_soup(soup)
        if not post_info.title or not post_info.user_name:
            raise ScrapeError(422)

        files: list[URL] = []
        for selector in (_POST.VIDEOS, _POST.IMAGES, _POST.ATTACHMENTS):
            for file in soup.select(selector):
                files.append(self.parse_url(file["href"]))  # type: ignore

        post = Post(
            user=url_info.user,
            user_name=post_info.user_name,
            id=url_info.post_id,
            title=post_info.title,
            content=post_info.content,
            _published=post_info.date,  # type: ignore
            soup_attachments=files,
        )
        await self._handle_post(scrape_item, post)
