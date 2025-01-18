from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class RedGifsCrawler(Crawler):
    primary_base_domain = URL("https://redgifs.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "redgifs", "RedGifs")
        self.redgifs_api = URL("https://api.redgifs.com/")
        self.headers = {}

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        await self.manage_token(self.redgifs_api / "v2/auth/temporary")

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        if "users" in scrape_item.url.parts:
            await self.user(scrape_item)
        else:
            await self.post(scrape_item)

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a users page."""
        user_id = scrape_item.url.parts[-1].split(".")[0]

        page = 1
        total_pages = 1

        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)

        while page <= total_pages:
            async with self.request_limiter:
                api_url = self.redgifs_api / "v2/users" / user_id / "search"
                url = api_url.with_query(f"order=new&count=40&page={page}")
                JSON_Resp = await self.client.get_json(self.domain, url, headers_inc=self.headers, origin=scrape_item)
            total_pages = JSON_Resp["pages"]
            gifs = JSON_Resp["gifs"]
            for gif in gifs:
                links: dict[str, str] = gif["urls"]
                date = gif["createDate"]
                title = self.create_title(user_id)

                link_str: str = links.get("hd") or links.get("sd")
                link = self.parse_url(link_str)
                filename, ext = get_filename_and_ext(link.name)
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    part_of_album=True,
                    possible_datetime=date,
                    add_parent=scrape_item.url,
                )
                await self.handle_file(link, new_scrape_item, filename, ext)
                scrape_item.add_children()
            page += 1

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a post."""
        post_id = scrape_item.url.parts[-1].split(".")[0]
        async with self.request_limiter:
            api_url = self.redgifs_api / "v2/gifs" / post_id
            JSON_Resp = await self.client.get_json(self.domain, api_url, headers_inc=self.headers, origin=scrape_item)

        title_part = JSON_Resp["gif"].get("title", "Loose Files")
        title = self.create_title(title_part)
        links: dict[str, str] = JSON_Resp["gif"]["urls"]
        date = JSON_Resp["gif"]["createDate"]

        link_str: str = links.get("hd") or links.get("sd")
        link = self.parse_url(link_str)

        filename, ext = get_filename_and_ext(link.name)
        new_scrape_item = self.create_scrape_item(
            scrape_item,
            link,
            title,
            part_of_album=True,
            possible_datetime=date,
            add_parent=scrape_item.url,
        )
        await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def manage_token(self, token_url: URL) -> None:
        """Gets/Sets the redgifs token and header."""
        async with self.request_limiter:
            json_obj = await self.client.get_json(self.domain, token_url)
        token = json_obj["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
