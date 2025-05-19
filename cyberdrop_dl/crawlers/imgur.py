from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import LoginError, ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

API_ENTRYPOINT = URL("https://api.imgur.com/3/")


class ImgurCrawler(Crawler):
    primary_base_domain = URL("https://imgur.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imgur", "Imgur")
        self.imgur_client_id = self.manager.config_manager.authentication_data.imgur.client_id
        self.imgur_client_remaining = 12500
        self.headers = {"Authorization": f"Client-ID {self.imgur_client_id}"}

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if scrape_item.url.host == "i.imgur.com":
            return await self.handle_direct_link(scrape_item)
        if "a" in scrape_item.url.parts:
            return await self.album(scrape_item)
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        await self.image(scrape_item)

    async def gallery(self, scrape_item: ScrapeItem) -> None:
        album_id = scrape_item.url.name.rsplit("-", 1)[-1]
        scrape_item.url = self.primary_base_domain / "a" / album_id
        await self.album(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        if not self.imgur_client_id:
            msg = "No Imgur Client ID provided"
            raise LoginError(msg)

        album_id = scrape_item.url.parts[-1]
        title: str = ""

        async with self.request_limiter:
            await self.check_imgur_credits(scrape_item)
            api_url = API_ENTRYPOINT / "album" / album_id
            json_resp: dict[str, dict] = await self.client.get_json(self.domain, api_url, headers=self.headers)

        title_part = json_resp["data"].get("title", album_id)
        title = self.create_title(title_part, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        async with self.request_limiter:
            api_url = API_ENTRYPOINT / "album" / album_id / "images"
            json_resp = await self.client.get_json(self.domain, api_url, headers=self.headers)

        for image in json_resp["data"]:
            await self.process_image(scrape_item, image)

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if not self.imgur_client_id:
            msg = "No Imgur Client ID provided"
            raise LoginError(msg)

        image_id = scrape_item.url.parts[-1]
        async with self.request_limiter:
            await self.check_imgur_credits(scrape_item)
            api_url = API_ENTRYPOINT / "image" / image_id
            json_resp = await self.client.get_json(self.domain, api_url, headers=self.headers)

        await self.process_image(scrape_item, json_resp["data"])

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        link = scrape_item.url
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        if ext.lower() in (".gifv", ".mp4"):
            filename_path = Path(filename).with_suffix(".mp4")
            file_id = filename_path.stem
            filename, ext = self.get_filename_and_ext(str(filename_path))
            link = URL("https://imgur.com/download") / file_id

        await self.handle_file(link, scrape_item, filename, ext)

    async def process_image(self, scrape_item: ScrapeItem, image_data: dict[str, Any]) -> None:
        link = self.parse_url(image_data["link"])
        new_scrape_item = scrape_item.create_child(link, possible_datetime=image_data["datetime"])
        await self.handle_direct_link(new_scrape_item)
        scrape_item.add_children()

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def check_imgur_credits(self, _=None) -> None:
        """Checks the remaining credits."""
        credits_url = API_ENTRYPOINT / "credits"
        json_resp = await self.client.get_json(self.domain, credits_url, headers=self.headers)
        self.imgur_client_remaining = json_resp["data"]["ClientRemaining"]
        if self.imgur_client_remaining < 100:
            raise ScrapeError(429, "Imgur API rate limit reached")
