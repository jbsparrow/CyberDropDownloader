from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class PixHostCrawler(Crawler):
    primary_base_domain = URL("https://pixhost.to/")
    update_unsupported = True

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pixhost", "PixHost")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if is_thumbnail(scrape_item.url):
            await self.handle_direct_link(scrape_item)
        elif "gallery" in scrape_item.url.parts:
            await self.gallery(scrape_item)
        elif "show" in scrape_item.url.parts:
            await self.image(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a gallery."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        album_id = scrape_item.url.name
        title = soup.select_one("a[class=link] h2").text  # type: ignore
        title = self.create_title(title, album_id)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True
        scrape_item.album_id = album_id
        results = await self.get_album_results(album_id)

        images = soup.select("div[class=images] a")
        for image in images:
            link_str: str = image.get("href")  # type: ignore
            thumb_link_str: str = image.select_one("img").get("src")  # type: ignore
            if not (thumb_link_str and link_str):
                continue
            link = self.parse_url(link_str)
            thumb_link = self.parse_url(thumb_link_str)
            if not self.check_album_results(link, results):
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                await self.handle_direct_link(new_scrape_item, thumb_link)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link_str: str = soup.select_one("img[class=image-img]").get("src")  # type: ignore
        link = self.parse_url(link_str)
        await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None = None):
        link = url or scrape_item.url
        if is_thumbnail(link):
            link = self.thumbnail_to_img(link)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    def thumbnail_to_img(self, url: URL):
        assert url.host
        thumb_server_id: str = url.host.split(".", 1)[0].split("t")[-1]
        img_host = f"img{thumb_server_id}.{self.primary_base_domain.host}"
        new_parts = ["images"] + [p for p in url.parts if p not in ("thumbs", "/")]
        new_path = "/".join(new_parts)
        return url.with_host(img_host).with_path(new_path)


def is_thumbnail(url: URL) -> bool:
    assert url.host
    return "thumbs" in url.parts and len(url.host.split(".")) >= 2
