from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import LoginError, ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class ImgurCrawler(Crawler):
    primary_base_domain = URL("https://imgur.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imgur", "Imgur")
        self.imgur_api = URL("https://api.imgur.com/3/")
        self.imgur_client_id = self.manager.config_manager.authentication_data.imgur.client_id
        self.imgur_client_remaining = 12500
        self.headers = {"Authorization": f"Client-ID {self.imgur_client_id}"}

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if scrape_item.url.host == "i.imgur.com":
            await self.handle_direct(scrape_item)
        elif "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        elif "gallery" in scrape_item.url.parts:
            await self.gallery(scrape_item)
        else:
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

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        album_id = scrape_item.url.parts[-1]
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True

        async with self.request_limiter:
            await self.check_imgur_credits(scrape_item)
            api_url = self.imgur_api / "album" / album_id
            JSON_Obj = await self.client.get_json(self.domain, api_url, headers_inc=self.headers, origin=scrape_item)

        title_part = JSON_Obj["data"].get("title", album_id)
        title = self.create_title(title_part, album_id)

        async with self.request_limiter:
            api_url = self.imgur_api / "album" / album_id / "images"
            JSON_Obj = await self.client.get_json(self.domain, api_url, headers_inc=self.headers, origin=scrape_item)

        for image in JSON_Obj["data"]:
            link_str: str = image["link"]
            link = self.parse_url(link_str)
            date = image["datetime"]
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                link,
                title,
                possible_datetime=date,
                add_parent=scrape_item.url,
            )
            await self.handle_direct(new_scrape_item)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if not self.imgur_client_id:
            msg = "No Imgur Client ID provided"
            raise LoginError(msg)

        image_id = scrape_item.url.parts[-1]
        async with self.request_limiter:
            await self.check_imgur_credits(scrape_item)
            api_url = self.imgur_api / "image" / image_id
            JSON_Obj = await self.client.get_json(self.domain, api_url, headers_inc=self.headers, origin=scrape_item)

        date = JSON_Obj["data"]["datetime"]
        link_str: str = JSON_Obj["data"]["link"]
        link = self.parse_url(link_str)
        new_scrape_item = self.create_scrape_item(scrape_item, link, possible_datetime=date)
        await self.handle_direct(new_scrape_item)

    @error_handling_wrapper
    async def handle_direct(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        if ext.lower() in (".gifv", ".mp4"):
            filename = filename.replace(ext, ".mp4")
            file_id = filename.rsplit(".", 1)[0]
            ext = ".mp4"
            link = URL("https://imgur.com/download") / file_id
            new_scrape_item = self.create_scrape_item(scrape_item, link)
            return await self.handle_file(link, new_scrape_item, filename, ext)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def check_imgur_credits(self, scrape_item: ScrapeItem | None = None) -> None:
        """Checks the remaining credits."""
        credits_url = self.imgur_api / "credits"
        credits_obj = await self.client.get_json(self.domain, credits_url, headers_inc=self.headers, origin=scrape_item)
        self.imgur_client_remaining = credits_obj["data"]["ClientRemaining"]
        if self.imgur_client_remaining < 100:
            raise ScrapeError(429, "Imgur API rate limit reached", origin=scrape_item)
