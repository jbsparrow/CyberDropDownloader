from __future__ import annotations

import calendar
import datetime

import calendar
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from dateutil import parser
from yarl import URL

from cyberdrop_dl import __version__
from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem, FILE_HOST_PROFILE
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager


class SexDotComCrawler(Crawler):
    primary_base_domain = URL("https://sex.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "sex", "Sex.com")
        self.api_url = URL("https://iframe.sex.com/api/")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        parts = scrape_item.url.parts
        if len(parts) > 5:
            await self.post(scrape_item)
        elif len(parts) <= 5 and parts[2] == "shorts":
            await self.profile(scrape_item)


    async def shorts_profile_paginator(self, scrape_item: ScrapeItem) -> AsyncGenerator[dict]:
        username = scrape_item.url.parts[3]
        page = 1
        while True:
            posts_api_url = self.api_url / "feed" / "listUserItems"

            query = {
                "pageSize": 300,
                "pageNumber": page,
                "visibility": "public",
                "username": username,
            }

            posts_api_url = posts_api_url.with_query(query)
            async with self.request_limiter:
                json_data = await self.client.get_json(self.domain, posts_api_url, origin=scrape_item)

            if scrape_item.album_id is None:
                user_id = json_data["page"]["items"][0]["media"]["user"]["userUid"]
                scrape_item.album_id = user_id
                scrape_item.add_to_parent_title(self.create_title(username))

            yield json_data

            if not json_data["page"]["pageInfo"]["hasNextPage"]:
                break
            page += 1

    @error_handling_wrapper
    async def get_media(self, scrape_item: ScrapeItem) -> dict:
        """Gets media from its relative URL."""
        relative_url = "/".join(scrape_item.url.parts[3:])
        data_url = self.api_url / "media" / "getMedia"
        query = {
            "relativeUrl": relative_url,
        }
        data_url = data_url.with_query(query)
        async with self.request_limiter:
            json_data = await self.client.get_json(self.domain, data_url, origin=scrape_item)
        return json_data["media"]

    @error_handling_wrapper
    async def handle_media(self, scrape_item: ScrapeItem, item: dict = None) -> None:
        if item is None:
            item = await self.get_media(scrape_item)
        relative_url = item["relativeUrl"]
        canonical_url = URL('https://sex.com/en/shorts') / relative_url
        if await self.check_complete_from_referer(canonical_url):
            return

        fileType = item.get("fileType") or item.get("mediaType")
        if fileType.startswith("image"):
            media_url = URL(item["fullPath"]).with_query({
                "optimizer": "image",
                "width": 1200,
            })
            filename = f"{item["pictureUid"]}.jpg"
            ext = "jpg"
        elif fileType.startswith("video"):
            media_url = URL(item["sources"][0]["fullPath"])
            filename, ext = get_filename_and_ext(media_url.name)
        date = self.parse_datetime(item["createdAt"])
        new_scrape_item = self.create_scrape_item(scrape_item, canonical_url, "", True, scrape_item.album_id, date)
        await self.handle_file(media_url, new_scrape_item, filename, ext)
        scrape_item.add_children()


    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes shorts."""
        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)
        async for json_data in self.shorts_profile_paginator(scrape_item):
            for item in json_data["page"]["items"]:
                await self.handle_media(scrape_item, item["media"])

    async def post(self, scrape_item: ScrapeItem):
        """Scrapes a post."""
        username = scrape_item.url.parts[2]
        scrape_item.add_to_parent_title(self.create_title(username))
        await self.handle_media(scrape_item)



    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = parser.isoparse(date)
        return calendar.timegm(parsed_date.utctimetuple())
