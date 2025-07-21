from __future__ import annotations

import dataclasses
import itertools
from typing import TYPE_CHECKING, Any, ClassVar, Required, TypedDict

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper, parse_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterable

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.utils.dates import TimeStamp

# Primary URL needs `www.` to prevent redirect
PRIMARY_URL = AbsoluteHttpURL("https://www.redgifs.com/")
API_ENTRYPOINT = AbsoluteHttpURL("https://api.redgifs.com/")


class Links(TypedDict, total=False):
    sd: Required[str]
    hd: str


@dataclasses.dataclass(frozen=True, slots=True)
class Gif:
    id: str
    urls: Links
    date: TimeStamp
    url: AbsoluteHttpURL
    title: str | None = None

    @staticmethod
    def from_dict(gif: dict[str, Any]) -> Gif:
        urls: Links = gif["urls"]
        url = parse_url(urls.get("hd") or urls["sd"], relative_to=PRIMARY_URL)
        return Gif(gif["id"], urls, gif["createDate"], url, gif.get("title"))


class RedGifsCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "User": "/users/<user>",
        "Gif": "/watch/<gif_id>",
        "Embeds": "/ifr/<gif_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "redgifs"
    FOLDER_DOMAIN: ClassVar[str] = "RedGifs"

    def __post_init__(self) -> None:
        self.headers = {}

    async def async_startup(self) -> None:
        await self.get_auth_token(API_ENTRYPOINT / "v2/auth/temporary")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["users", user_name]:
                return await self.user(scrape_item, _id(user_name))
            case ["watch" | "ifr", gif_id]:
                return await self.gif(scrape_item, _id(gif_id))

        if self.is_self_subdomain(scrape_item.url) and len(scrape_item.url.parts) == 2:
            scrape_item.url = _canonical_url(scrape_item.url.name)
            self.manager.task_group.create_task(self.run(scrape_item))
            return

        raise ValueError

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, user_id: str) -> None:
        title = self.create_title(user_id)
        scrape_item.setup_as_album(title)

        async for gifs in self._user_profile_pager(user_id):
            for gif in gifs:
                new_scrape_item = scrape_item.create_child(_canonical_url(gif.id))
                await self._handle_gif(new_scrape_item, gif)
                scrape_item.add_children()

    async def _user_profile_pager(self, user_id: str) -> AsyncIterable[list[Gif]]:
        total_pages: int | None = None
        for page in itertools.count(1):
            async with self.request_limiter:
                api_url = API_ENTRYPOINT / "v2/users" / user_id / "search"
                api_url = api_url.with_query(order="new", page=page)
                json_resp: dict[str, Any] = await self.client.get_json(self.DOMAIN, api_url, headers=self.headers)

            gifs_in_current_page = [Gif.from_dict(gif) for gif in json_resp["gifs"]]
            yield gifs_in_current_page

            # The "pages" values of the json response is only the number of pages to get the first 1K gifs
            # We have to manually compute the actual number of pages to handle profiles with 1K+ gifs
            if total_pages is None:
                total_gifs: int = json_resp["users"][0]["gifs"]
                total_pages, res = divmod(total_gifs, len(gifs_in_current_page))
                total_pages += bool(res)
            if page >= total_pages:
                break

    @error_handling_wrapper
    async def gif(self, scrape_item: ScrapeItem, post_id: str) -> None:
        canonical_url = _canonical_url(post_id)
        if await self.check_complete_from_referer(canonical_url):
            return

        scrape_item.url = canonical_url
        async with self.request_limiter:
            api_url = API_ENTRYPOINT / "v2/gifs" / post_id
            json_resp: dict[str, dict] = await self.client.get_json(self.DOMAIN, api_url, headers=self.headers)

        gif = Gif.from_dict(json_resp["gif"])
        if gif.title:
            scrape_item.setup_as_album(self.create_title(gif.title))
        await self._handle_gif(scrape_item, gif)

    async def _handle_gif(self, scrape_item: ScrapeItem, gif: Gif) -> None:
        scrape_item.possible_datetime = gif.date
        filename, ext = self.get_filename_and_ext(gif.url.name)
        await self.handle_file(gif.url, scrape_item, filename, ext)

    @error_handling_wrapper
    async def get_auth_token(self, token_url: AbsoluteHttpURL) -> None:
        async with self.request_limiter:
            json_obj = await self.client.get_json(self.DOMAIN, token_url)
        token: str = json_obj["token"]
        self.headers = {"Authorization": f"Bearer {token}"}


def _id(name: str) -> str:
    # PaleturquoiseLostStickinsect-mobile.m4s -> paleturquoiseLoststickinsect
    # Id needs to be lower case for requests to the api, but final files (media.redgifs) need each word capitalized
    return name.lower().split(".", 1)[0].split("-", 1)[0]


def _canonical_url(name_or_id: str) -> AbsoluteHttpURL:
    return PRIMARY_URL / "watch" / _id(name_or_id)


def fix_db_referer(referer: str) -> str:
    url = AbsoluteHttpURL(referer)
    name = url.name or url.parent.name
    return str(_canonical_url(name))
