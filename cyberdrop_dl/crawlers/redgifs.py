from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://redgifs.com/")
API_ENTRYPOINT = AbsoluteHttpURL("https://api.redgifs.com/")


class RedGifsCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"User": "/users/<user>", "Video": "/watch/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "redgifs"
    FOLDER_DOMAIN: ClassVar[str] = "RedGifs"

    def __post_init__(self) -> None:
        self.headers = {}

    async def async_startup(self) -> None:
        await self.get_auth_token(API_ENTRYPOINT / "v2/auth/temporary")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "users" in scrape_item.url.parts:
            return await self.user(scrape_item)
        await self.post(scrape_item)

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem) -> None:
        user_id = scrape_item.url.parts[-1].split(".")[0]
        title = self.create_title(user_id)
        scrape_item.setup_as_album(title)

        async for json_resp in self.user_profile_pager(scrape_item):
            for gif in json_resp["gifs"]:
                links: dict[str, str] = gif["urls"]
                date: int = gif["createDate"]
                link_str: str = links.get("hd") or links["sd"]
                link = self.parse_url(link_str)
                filename, ext = self.get_filename_and_ext(link.name)
                new_scrape_item = scrape_item.create_child(link, possible_datetime=date)
                await self.handle_file(link, new_scrape_item, filename, ext)
                scrape_item.add_children()

    async def user_profile_pager(self, scrape_item: ScrapeItem):
        page = total_pages = 1
        total_gifs = None
        user_id = scrape_item.url.parts[-1].split(".")[0]
        while page <= total_pages:
            async with self.request_limiter:
                api_url = API_ENTRYPOINT / "v2/users" / user_id / "search"
                api_url = api_url.with_query(order="new", page=page)
                json_resp = await self.client.get_json(self.DOMAIN, api_url, headers=self.headers)
            gifs = json_resp["gifs"]
            yield json_resp
            if total_gifs is None:
                total_gifs = json_resp["users"][0]["gifs"]
                total_pages, res = divmod(total_gifs, len(gifs))
                total_pages += bool(res)
            page += 1

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        post_id = scrape_item.url.parts[-1].split(".")[0]
        async with self.request_limiter:
            api_url = API_ENTRYPOINT / "v2/gifs" / post_id
            json_resp: dict[str, dict] = await self.client.get_json(self.DOMAIN, api_url, headers=self.headers)

        title_part: str = json_resp["gif"].get("title") or "Loose Files"
        title = self.create_title(title_part)
        scrape_item.setup_as_album(title)
        scrape_item.possible_datetime = json_resp["gif"]["createDate"]

        links: dict[str, str] = json_resp["gif"]["urls"]
        link_str: str = links.get("hd") or links["sd"]
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def get_auth_token(self, token_url: AbsoluteHttpURL) -> None:
        async with self.request_limiter:
            json_obj = await self.client.get_json(self.DOMAIN, token_url)
        token = json_obj["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
