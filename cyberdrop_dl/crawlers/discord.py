from __future__ import annotations

import asyncio
import calendar
import datetime
from dataclasses import dataclass
from datetime import datetime
from json import dumps
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


@dataclass(frozen=True, slots=True)
class discordURLData:
    server_id: str
    channel_id: str
    message_id: str

    @property
    def is_dm(self) -> bool:
        return self.server_id == "@me"


class DiscordCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"discord": ["discord", "discordapp", "fixcdn.hyonsu"]}
    primary_base_domain = URL("https://discord.com/")

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, "discord", "Discord")
        self.api_url = URL("https://discord.com/api/")
        self.request_limiter = AsyncLimiter(5, 2)
        self.headers = {
            "Authorization": self.manager.config_manager.authentication_data.discord.token,
            "Content-Type": "application/json",
        }

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "channels" in scrape_item.url.parts:
            parts = scrape_item.url.parts
            if len(parts) > 2 and len(parts) < 5:
                # Server/DM or Channel/Group DM
                await self.get_media(scrape_item)
        elif "attachments" in scrape_item.url.parts:
            await self.file(scrape_item)

    async def get_canonical_url(self, url: URL) -> URL:
        """Gets the canonical URL for a given URL."""
        # Normalize CDN fix URLs
        url.with_host("cdn.discordapp.com")
        return url

    async def get_info(self, scrape_item: ScrapeItem) -> discordURLData:
        """Gets the server, channel, and message IDs from the URL."""
        parts = scrape_item.url.parts
        info = (
            parts[2] if len(parts) > 2 else "",
            parts[3] if len(parts) > 3 else "",
            parts[4] if len(parts) > 4 else "",
        )
        return discordURLData(*info)

    async def get_search_request_data(self, scrape_item: ScrapeItem) -> tuple[dict, URL]:
        """Gets the JSON request to use for the desired search."""
        data = await self.get_info(scrape_item)

        request_json = {
            "tabs": {
                "media": {
                    "sort_by": "timestamp",
                    "sort_order": "asc",
                    "has": ["image", "video"],
                    "cursor": None,
                    "limit": 25,
                }
            },
            "track_exact_total_hits": True,
        }

        if data.channel_id and not data.is_dm:
            request_json["channel_ids"] = [data.channel_id]
        if not data.is_dm:
            request_json["include_nsfw"] = True

        if data.is_dm:
            # Dicord DM API paths. First case is to scrape a single DM/Group DM. Second case is to scrape all DMs.
            path = ("channels", data.channel_id) if data.channel_id else ("users", "@me")
        else:
            # Discord server API path. Always the same, channel IDs are handled by the JSON.
            path = ("guilds", data.server_id)

        request_url = self.api_url / "v9" / path[0] / path[1] / "messages" / "search" / "tabs"
        return request_json, request_url

    async def search_media(self, scrape_item: ScrapeItem) -> AsyncGenerator[dict, None]:
        """Uses the Discord mobile app search API to find media."""
        request_json, request_url = await self.get_search_request_data(scrape_item)

        while True:
            async with self.request_limiter:
                data = await self.client.post_data(
                    self.domain, url=request_url, data=dumps(request_json), origin=scrape_item, headers_inc=self.headers
                )
                if "rate limited" in data.get("message", ""):
                    wait_time = data.get("retry_after", 0)
                    await asyncio.sleep(wait_time * 1.2)
                    continue
                media = data.get("tabs", {}).get("media", {})
                messages = media.get("messages", [])

                if messages:
                    timestamp = media.get("cursor", {}).get("timestamp")
                    yield messages
                else:
                    break

                if timestamp:
                    request_json["tabs"]["media"]["cursor"] = {"timestamp": timestamp, "type": "timestamp"}

    @error_handling_wrapper
    async def get_media(self, scrape_item: ScrapeItem) -> None:
        """Gets the media from the Discord mobile app search API."""
        async for messages in self.search_media(scrape_item):
            for message in messages:
                await self.process_attachments(message[0], scrape_item)

    async def process_attachments(self, message: dict, scrape_item: ScrapeItem) -> None:
        for attachment in message.get("attachments"):
            file_id = attachment.get("id", 0)
            url = attachment.get("url")
            filename = attachment.get("filename")
            size = attachment.get("size", 0)
            content_type = attachment.get("content_type")
            width = attachment.get("width", 0)
            height = attachment.get("height", 0)
            user_id = message.get("author", {}).get("id")
            username = message.get("author", {}).get("username")
            channel_id = message.get("channel_id")
            timestamp = self.parse_datetime(message.get("timestamp"))

            canonical_url = await self.get_canonical_url(scrape_item.url)
            if await self.check_complete_from_referer(canonical_url):
                continue
            new_scrape_item = scrape_item.create_new(
                url=canonical_url,
                new_title_part=f"{username} ({user_id})",
                possible_datetime=timestamp,
                add_parent=True,
            )

            filename, ext = get_filename_and_ext(filename)
            await self.handle_file(url=URL(url), scrape_item=new_scrape_item, filename=filename, ext=ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        canonical_url = await self.get_canonical_url(scrape_item.url)
        if await self.check_complete_from_referer(canonical_url):
            return

        new_scrape_item = scrape_item.create_new(parent_scrape_item=scrape_item, url=canonical_url, add_parent=True)

        filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = date.split("+")[0]
        dt = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f")
        return calendar.timegm(dt.timetuple())
