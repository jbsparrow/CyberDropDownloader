from __future__ import annotations

import random
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import LoginError, ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


PRIMARY_BASE_DOMAIN = URL("https://nhentai.net/")
API_ENTRYPOINT = PRIMARY_BASE_DOMAIN / "api/gallery/"
EXT_MAP = {"a": ".avif", "g": ".gif", "j": ".jpg", "p": ".png", "w": ".webp"}
COLLECTION_PARTS = "favorites", "tag", "search", "parody", "group", "character", "artist"
ITEM_SELECTOR = "div.gallery > a"
COLLECTION_TITLE_SELECTOR = "div#content > h1"


class NHentaiCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN
    next_page_selector = "a.next"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "nhentai.net", "nHentai")
        self.request_limiter = AsyncLimiter(4, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p in scrape_item.url.parts for p in COLLECTION_PARTS):
            return await self.collection(scrape_item)
        if "g" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        collection_type = title = ""
        async for soup in self.web_pager(scrape_item):
            if not collection_type:
                title_tag = soup.select_one(COLLECTION_TITLE_SELECTOR)
                if not title_tag:
                    raise ScrapeError(422)

                for part in COLLECTION_PARTS:
                    if part in scrape_item.url.parts:
                        collection_type = part
                        break

                if collection_type == "favorites":
                    if soup.select_one("input.id_username_or_email"):
                        raise LoginError("No cookies provided to download favorites")

                    for span in soup.find_all("span"):
                        span.decompose()

                else:
                    title_tag = soup.select_one("span.name")
                    title = f" [{collection_type}]"

                title: str = title_tag.get_text(strip=True) + title  # type: ignore
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            for item in soup.select(ITEM_SELECTOR):
                link_str: str = item.get("href")  # type: ignore
                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        gallery_id = scrape_item.url.name
        api_url = API_ENTRYPOINT / gallery_id
        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.domain, api_url)

        log_debug(json_resp)
        titles: dict[str, str] = json_resp["title"]
        title: str = titles.get("english") or titles.get("japanese") or titles["pretty"]
        title = self.create_title(title, gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)
        scrape_item.possible_datetime = json_resp["upload_date"]

        n_images: int = json_resp["num_pages"]
        padding = max(3, len(str(n_images)))
        for index, link in get_image_urls(json_resp):
            filename, ext = get_filename_and_ext(link.name)
            custom_filename = f"{index:0{padding}d}{ext}"
            await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_image_urls(json_resp: dict) -> Generator[tuple[int, URL]]:
    media_id: str = json_resp["media_id"]
    for index, info in enumerate(json_resp["images"]["pages"], 1):
        ext = EXT_MAP.get(info["t"]) or ".jpg"
        cdn = random.randint(1, 4)
        yield index, URL(f"https://i{cdn}.nhentai.net/galleries/{media_id}/{index}{ext}")
