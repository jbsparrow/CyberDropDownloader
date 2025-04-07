from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


GALLERY_TITLE_SELECTOR = "a#gallery-name"
IMAGES_SELECTOR = "ul.images a.thumbnail"
IMAGE_SELECTOR = "img.main-image"
GALLERY_INFO_SELECTOR = "div.view-navigation a:has(i.fas.fa-reply)"
PRIMARY_BASE_DOMAIN = URL("https://www.imagebam.com/")


class ImageBamCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imagebam", "ImageBam")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        self.set_cookies()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if is_cdn(scrape_item.url):
            scrape_item.url = get_view_url(scrape_item.url)
        if any(part in scrape_item.url.parts for part in ("gallery", "image", "view")):
            return await self.view(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def view(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        if "Share this gallery" in soup.text:
            return await self.gallery(scrape_item, soup)
        await self.image(scrape_item, soup)

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        gallery_name = soup.select_one(GALLERY_TITLE_SELECTOR).get_text()  # type: ignore
        gallery_id = scrape_item.url.name
        title = self.create_title(gallery_name, gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)
        results = await self.get_album_results(gallery_id)

        for _, new_scrape_item in self.iter_children(scrape_item, soup.select(IMAGES_SELECTOR)):
            if not self.check_album_results(new_scrape_item.url, results):
                self.manager.task_group.create_task(self.image(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        image_tag = soup.select_one(IMAGE_SELECTOR)
        if not image_tag:
            raise ScrapeError(422)

        gallery_info = soup.select_one(GALLERY_INFO_SELECTOR)
        if gallery_info and not scrape_item.album_id:
            gallery_url = self.parse_url(gallery_info.get("href"))  # type: ignore
            gallery_id = gallery_url.name
            scrape_item.album_id = gallery_id

        title: str = image_tag["alt"]  # type: ignore
        link = self.parse_url(image_tag["src"])  # type: ignore
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename, _ = self.get_filename_and_ext(title)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def set_cookies(self) -> None:
        """Set cookies to bypass confirmation."""
        cookies = {"nsfw_inter": "1"}
        self.update_cookies(cookies)


def is_cdn(url: URL) -> bool:
    assert url.host
    return "imagebam" in url.host.split(".") and "." in url.host.rstrip(".com")


def get_view_url(url: URL) -> URL:
    view_id = url.name.rsplit("_", 1)[0]
    return PRIMARY_BASE_DOMAIN / "view" / view_id
