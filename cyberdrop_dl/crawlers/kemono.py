from __future__ import annotations

import calendar
import re
from typing import TYPE_CHECKING, Any, NamedTuple, TypedDict

from pydantic import AliasChoices, Field
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError
from cyberdrop_dl.config_definitions.custom.types import AliasModel
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, remove_parts

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import datetime

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

PRIMARY_BASE_DOMAIN = URL("https://kemono.su")
LINK_REGEX = re.compile(r"(?:http(?!.*\.\.)[^ ]*?)(?=($|\n|\r\n|\r|\s|\"|\[/URL]|']\[|]\[|\[/img]|</|'))")


class File(TypedDict):
    name: str
    path: str


class UserInfo(NamedTuple):
    service: str
    user: str
    post: str | None
    user_str: str


class KemonoPost(AliasModel):
    user: str
    id: str
    title: str
    file: File | None = None
    content: str = ""
    attachments: list[File] = []  # noqa: RUF012
    _published: datetime = Field(validation_alias=AliasChoices("published", "added"))

    def model_post_init(self):
        self.date = calendar.timegm(self._published.timetuple())

    @property
    def all_files(self) -> Generator[File]:
        if self.file:
            yield self.file
        yield from self.attachments


API_ENTRYPOINT = URL("https://kemono.su/api/v1")
SERVICES = "afdian", "boosty", "dlsite", "fanbox", "fantia", "gumroad", "patreon", "subscribestar"


def _api_w_offset(path: str, og_url: URL) -> tuple[str, URL]:
    api_url = API_ENTRYPOINT / path
    offset = int(og_url.query.get("o", 0))
    if query := og_url.query.get("q"):
        return query, api_url.update_query(o=offset, q=query)
    return "", api_url.update_query(o=offset)


class KemonoCrawler(Crawler):
    primary_base_domain = URL("https://kemono.su")
    DEFAULT_POST_TITLE_FORMAT = "{date} - {title}"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "kemono", "Kemono")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "thumbnails" in scrape_item.url.parts:
            scrape_item.url = remove_parts(scrape_item.url, "thumbnails")
            return await self.handle_direct_link(scrape_item)
        if "discord" in scrape_item.url.parts:
            return await self.discord(scrape_item)
        if "post" in scrape_item.url.parts:
            return await self.post(scrape_item)
        if scrape_item.url.name == "posts" and scrape_item.url.query.get("q"):
            return await self.search(scrape_item)
        if any(x in scrape_item.url.parts for x in SERVICES):
            return await self.profile(scrape_item)
        await self.handle_direct_link(scrape_item)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        """Scrapes results from a search query."""
        query, api_url = _api_w_offset("posts", scrape_item.url)
        title = self.create_title(f"Search - {query}")
        scrape_item.setup_as_album(title)
        await self.iter_from_url(scrape_item, api_url)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        info = await self.get_user_info(scrape_item)
        _, api_url = _api_w_offset(f"{info.service}/user/{info.user}", scrape_item.url)
        await self.iter_from_url(scrape_item, api_url)

    @error_handling_wrapper
    async def discord(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        channel = scrape_item.url.raw_fragment
        _, api_url = _api_w_offset(f"discord/channel/{channel}", scrape_item.url)
        await self.iter_from_url(scrape_item, api_url)

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a post."""
        user_info = await self.get_user_info(scrape_item)
        assert user_info.post
        path = f"{user_info.service}/user/{user_info.user}/post/{user_info.post}"
        _, api_url = _api_w_offset(path, scrape_item.url)
        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.domain, api_url)

        post = KemonoPost(**json_resp["post"])
        await self._handle_post(scrape_item, post)

    async def iter_from_url(self, scrape_item: ScrapeItem, url: URL):
        async for json_resp in self.api_pager(url):
            posts: list[dict[str, Any]] = json_resp.get("posts") or json_resp  # type: ignore
            for post in (KemonoPost(**entry) for entry in posts):
                await self._handle_post(scrape_item, post)

    async def api_pager(self, url: URL):
        offset = int(url.query.get("o") or 0)
        while True:
            api_url = url.update_query(o=offset)
            async with self.request_limiter:
                json_resp: dict = await self.client.get_json(self.domain, api_url)
            yield json_resp
            if not json_resp:
                break
            offset += 50

    async def _handle_post(self, scrape_item: ScrapeItem, post: KemonoPost):
        scrape_item.setup_as_album(post.title, album_id=post.id)
        scrape_item.possible_datetime = post.date
        post_title = self.create_separate_post_title(post.id, post.title, post.date)
        scrape_item.add_to_parent_title(post_title)
        for file in post.all_files:
            file_url = self._make_file_url(file)
            await self.handle_direct_link(scrape_item, file_url)
            scrape_item.add_children()
        self._handle_post_content(scrape_item, post)

    def _make_file_url(self, file: File) -> URL:
        return self.parse_url(f"/data/{file['path']}").with_query(f=file["name"])

    def _handle_post_content(self, scrape_item: ScrapeItem, post: KemonoPost) -> None:
        """Gets links out of content in post."""
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
            if not link.host or "kemono" in link.host:
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
            filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_user_info(self, scrape_item: ScrapeItem) -> UserInfo:
        """Gets the user info from a scrape item."""
        service, _, user = scrape_item.url.parts[1:4]
        try:
            post = scrape_item.url.parts[5]
        except IndexError:
            post = None

        api_url = API_ENTRYPOINT / service / "user" / user / "posts-legacy"
        async with self.request_limiter:
            profile_json, _ = await self.client.get_json(self.domain, api_url, cache_disabled=True)
        properties: dict = profile_json.get("props", {})

        user_str = properties.get("name", user)

        return UserInfo(service, user, post, user_str)
