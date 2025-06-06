from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from multidict import MultiDict

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.managers.real_debrid.api import RATE_LIMIT
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://real-debrid.com")


class RealDebridCrawler(Crawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "real-debrid"
    FOLDER_DOMAIN: ClassVar[str] = "RealDebrid"

    def __post_init__(self) -> None:
        self.headers = {}
        self.request_limiter = AsyncLimiter(RATE_LIMIT, 60)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = await self.get_original_url(scrape_item)
        if self.manager.real_debrid_manager.is_supported_folder(scrape_item.url):
            return await self.folder(scrape_item)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        self.log(f"Scraping folder with RealDebrid: {scrape_item.url}", 20)
        folder_id = self.manager.real_debrid_manager.guess_folder(scrape_item.url)
        title = self.create_title(f"{folder_id} [{scrape_item.url.host.lower()}]", folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)

        async with self.request_limiter:
            links = self.manager.real_debrid_manager.unrestrict_folder(scrape_item.url)

        for link in links:
            new_scrape_item = scrape_item.create_child(link)
            await self.file(new_scrape_item)
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        original_url = database_url = debrid_url = scrape_item.url
        password = original_url.query.get("password", "")

        if await self.check_complete_from_referer(original_url):
            return

        self_hosted = self.is_self_hosted(original_url)
        host = original_url.host.lower()

        if not self_hosted:
            title = self.create_title(f"files [{host}]")
            scrape_item.setup_as_album(title)
            async with self.request_limiter:
                debrid_url = self.manager.real_debrid_manager.unrestrict_link(original_url, password)

        if await self.check_complete_from_referer(debrid_url):
            return

        self.log(f"Real Debrid:\n  Original URL: {original_url}\n  Debrid URL: {debrid_url}", 10)

        if not self_hosted:
            # Some hosts use query params or fragment as id or password (ex: mega.nz)
            # This save the query and fragment as parts of the URL path since DB lookups only use url_path
            database_url = PRIMARY_URL / host / original_url.path[1:]
            if original_url.query:
                query_params_list = [item for pair in original_url.query.items() for item in pair]
                database_url = database_url / "query" / "/".join(query_params_list)

            if original_url.fragment:
                database_url = database_url / "frag" / original_url.fragment

        filename, ext = self.get_filename_and_ext(debrid_url.name)
        await self.handle_file(database_url, scrape_item, filename, ext, debrid_link=debrid_url)

    def is_self_hosted(self, url: AbsoluteHttpURL) -> bool:
        return any(subdomain in url.host for subdomain in ("download.", "my.")) and self.DOMAIN in url.host

    async def get_original_url(self, scrape_item: ScrapeItem) -> AbsoluteHttpURL:
        self.log(f"Input URL: {scrape_item.url}")
        if not self.is_self_hosted(scrape_item.url) or self.DOMAIN not in scrape_item.url.host:
            self.log(f"Parsed URL: {scrape_item.url}")
            return scrape_item.url

        parts_dict: dict[str, list[str]] = {"parts": [], "query": [], "frag": []}
        key = "parts"

        original_domain = scrape_item.url.parts[1]
        for part in scrape_item.url.parts[2:]:
            if part in ("query", "frag"):
                key = part
                continue
            parts_dict[key].append(part)

        path = "/".join(parts_dict["parts"])
        query = MultiDict()
        for i in range(0, len(parts_dict["query"]), 2):
            query[parts_dict["query"][i]] = parts_dict["query"][i + 1]

        frag = parts_dict["frag"][0] if parts_dict["frag"] else None
        parsed_url = (
            AbsoluteHttpURL(f"https://{original_domain}/{path}", encoded="%" in path)
            .with_query(query)
            .with_fragment(frag)
        )
        self.log(f"Parsed URL: {parsed_url}")
        return parsed_url
