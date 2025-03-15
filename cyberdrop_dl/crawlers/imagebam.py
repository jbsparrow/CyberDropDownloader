from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class ImageBamCrawler(Crawler):
    primary_base_domain = URL("https://www.imagebam.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imagebam", "ImageBam")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        self.set_cookies()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(part in scrape_item.url.parts for part in ("gallery", "image")):
            return await self.view(scrape_item)

        if self.is_cdn(scrape_item.url):
            scrape_item.url = self.get_view_url(scrape_item.url)

        if "view" not in scrape_item.url.parts:
            raise ValueError

        await self.view(scrape_item)

    @error_handling_wrapper
    async def view(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        if "Share this gallery" in soup.text:
            return await self.gallery(scrape_item, soup)

        await self.image(scrape_item, soup)

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem, soup: BeautifulSoup | None = None) -> None:
        if not soup:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        gallery_name = soup.select_one("a#gallery-name").get_text()
        gallery_id = scrape_item.url.name
        title = self.create_title(gallery_name, gallery_id)
        scrape_item.part_of_album = True
        scrape_item.album_id = gallery_id
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.add_to_parent_title(title)
        results = await self.get_album_results(gallery_id)

        images = soup.select("ul.images a.thumbnail")
        for image in images:
            link_str: str = image.get("href")
            link = self.parse_url(link_str)
            if not self.check_album_results(link, results):
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                self.manager.task_group.create_task(self.image(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem, soup: BeautifulSoup | None = None) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        if not soup:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        image_tag = soup.select_one("img.main-image")
        if not image_tag:
            raise ScrapeError(422, origin=scrape_item)

        from_gallery = soup.select_one("div.view-navigation a:has(i.fas.fa-reply)")
        if from_gallery and not scrape_item.album_id:
            gallery_url_str: str = from_gallery.get("href")
            gallery_url = self.parse_url(gallery_url_str)
            gallery_id = gallery_url.name
            scrape_item.album_id = gallery_id

        title: str = image_tag.get("alt")
        link_str: str = image_tag.get("src")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        custom_filename, _ = get_filename_and_ext(title)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def is_cdn(self, url: URL) -> bool:
        host: str = url.host
        return "imagebam" in host.split(".") and "." in host.rstrip(".com")

    def get_view_url(self, url: URL) -> URL:
        view_id = url.name.rsplit("_", 1)[0]
        return self.primary_base_domain / "view" / view_id

    def set_cookies(self) -> None:
        """Set cookies to bypass confirmation."""
        cookies = {"nsfw_inter": "1"}
        self.update_cookies(cookies)
