from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://sex.com")
API_URL = AbsoluteHttpURL("https://iframe.sex.com/api/")


class SexDotComCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Shorts Profiles": "/shorts/<profile>"}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "sex"
    FOLDER_DOMAIN: ClassVar[str] = "Sex.com"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        n_parts = len(scrape_item.url.parts)
        if n_parts > 5:
            return await self.post(scrape_item)
        if 3 <= n_parts <= 5 and scrape_item.url.parts[2] == "shorts":
            return await self.profile(scrape_item)
        raise ValueError

    async def shorts_profile_paginator(self, scrape_item: ScrapeItem) -> AsyncGenerator[dict]:
        username = scrape_item.url.parts[3]
        page = 1
        while True:
            posts_api_url = API_URL / "feed" / "listUserItems"
            query = {"pageSize": 300, "pageNumber": page, "visibility": "public", "username": username}
            posts_api_url = posts_api_url.with_query(query)
            async with self.request_limiter:
                json_data = await self.client.get_json(self.DOMAIN, posts_api_url)

            if scrape_item.album_id is None:
                user_id = json_data["page"]["items"][0]["media"]["user"]["userUid"]
                title = self.create_title(username, user_id)
                scrape_item.setup_as_profile(title, album_id=user_id)

            yield json_data

            if not json_data["page"]["pageInfo"]["hasNextPage"]:
                break
            page += 1

    async def get_media(self, scrape_item: ScrapeItem) -> dict[str, Any]:
        """Gets media from its relative URL."""
        relative_url = "/".join(scrape_item.url.parts[3:])
        data_url = API_URL / "media" / "getMedia"
        data_url = data_url.with_query(relativeUrl=relative_url)
        async with self.request_limiter:
            json_data = await self.client.get_json(self.DOMAIN, data_url)
        return json_data["media"]

    @error_handling_wrapper
    async def handle_media(self, scrape_item: ScrapeItem, item: dict[str, Any] | None) -> None:
        real_item = item or await self.get_media(scrape_item)
        relative_url = real_item["relativeUrl"]
        canonical_url = AbsoluteHttpURL("https://sex.com/en/shorts") / relative_url
        if await self.check_complete_from_referer(canonical_url):
            return

        fileType: str = real_item.get("fileType") or real_item["mediaType"]
        if fileType.startswith("image"):
            media_url = AbsoluteHttpURL(real_item["fullPath"]).with_query(optimizer="image", width=1200)
            filename, ext = f"{real_item['pictureUid']}.jpg", "jpg"

        elif fileType.startswith("video"):
            media_url = AbsoluteHttpURL(real_item["sources"][0]["fullPath"])
            filename, ext = self.get_filename_and_ext(media_url.name)
        else:
            return

        scrape_item.possible_datetime = self.parse_date(real_item["createdAt"])
        scrape_item.url = canonical_url
        await self.handle_file(media_url, scrape_item, filename, ext)
        scrape_item.add_children()

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        async for json_data in self.shorts_profile_paginator(scrape_item):
            for item in json_data["page"]["items"]:
                await self.handle_media(scrape_item, item["media"])

    async def post(self, scrape_item: ScrapeItem) -> None:
        username = scrape_item.url.parts[2]
        title = self.create_title(username)
        scrape_item.setup_as_album(title)
        await self.handle_media(scrape_item, None)
