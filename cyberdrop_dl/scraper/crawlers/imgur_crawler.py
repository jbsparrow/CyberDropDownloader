from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import LoginError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

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
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "i.imgur.com" in scrape_item.url.host:
            await self.handle_direct(scrape_item)
        elif "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        if self.imgur_client_id == "":
            log("To scrape imgur content, you need to provide a client id", 30)
            raise LoginError(message="No Imgur Client ID provided")
        await self.check_imgur_credits(scrape_item)
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        album_id = scrape_item.url.parts[-1]
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True

        async with self.request_limiter:
            JSON_Obj = await self.client.get_json(
                self.domain,
                self.imgur_api / f"album/{album_id}",
                headers_inc=self.headers,
                origin=scrape_item,
            )
        title_part = JSON_Obj["data"].get("title", album_id)
        title = self.create_title(title_part, scrape_item.url.parts[2])

        async with self.request_limiter:
            JSON_Obj = await self.client.get_json(
                self.domain,
                self.imgur_api / f"album/{album_id}/images",
                headers_inc=self.headers,
                origin=scrape_item,
            )

        for image in JSON_Obj["data"]:
            link_str: str = image["link"]
            link = URL(link_str, encoded="%" in link_str)
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
            log("To scrape imgur content, you need to provide a client id", 40)
            msg = "No Imgur Client ID provided"
            raise LoginError(msg)

        await self.check_imgur_credits(scrape_item)

        image_id = scrape_item.url.parts[-1]
        async with self.request_limiter:
            JSON_Obj = await self.client.get_json(
                self.domain,
                self.imgur_api / f"image/{image_id}",
                headers_inc=self.headers,
                origin=scrape_item,
            )

        date = JSON_Obj["data"]["datetime"]
        link_str: str = JSON_Obj["data"]["link"]
        link = URL(link_str, encoded="%" in link_str)
        new_scrape_item = self.create_scrape_item(scrape_item, link, possible_datetime=date)
        await self.handle_direct(new_scrape_item)

    @error_handling_wrapper
    async def handle_direct(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        filename, ext = get_filename_and_ext(scrape_item.url.name)
        if any(extension == ext.lower() for extension in (".gifv", ".mp4")):
            filename = filename.replace(ext, ".mp4")
            ext = ".mp4"
            link = URL("https://imgur.com/download").joinpath(filename.replace(ext, ""), encoded="%" in filename)
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
