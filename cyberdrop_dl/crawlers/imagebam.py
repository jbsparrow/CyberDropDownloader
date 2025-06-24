from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


GALLERY_TITLE_SELECTOR = "a#gallery-name"
IMAGES_SELECTOR = "ul.images a.thumbnail"
IMAGE_SELECTOR = "img.main-image"
GALLERY_INFO_SELECTOR = "div.view-navigation a:has(i.fas.fa-reply)"
PRIMARY_URL = AbsoluteHttpURL("https://www.imagebam.com/")


class ImageBamCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/view/...",
        "Image": "/view/...",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "imagebam"
    FOLDER_DOMAIN: ClassVar[str] = "ImageBam"

    async def async_startup(self) -> None:
        self.update_cookies({"nsfw_inter": "1"})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if is_cdn(scrape_item.url):
            scrape_item.url = get_view_url(scrape_item.url)
        if any(part in scrape_item.url.parts for part in ("gallery", "image", "view")):
            return await self.view(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def view(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        if "Share this gallery" in soup.text:
            return await self.gallery(scrape_item, soup)
        await self.image(scrape_item, soup)

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        gallery_name = css.select_one_get_text(soup, GALLERY_TITLE_SELECTOR)
        gallery_id = scrape_item.url.name
        title = self.create_title(gallery_name, gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)
        results = await self.get_album_results(gallery_id)

        for _, new_scrape_item in self.iter_children(scrape_item, soup, IMAGES_SELECTOR):
            if not self.check_album_results(new_scrape_item.url, results):
                self.manager.task_group.create_task(self.image(new_scrape_item, soup))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        image_tag = soup.select_one(IMAGE_SELECTOR)
        if not image_tag:
            raise ScrapeError(422)

        gallery_info = soup.select_one(GALLERY_INFO_SELECTOR)
        if gallery_info and not scrape_item.album_id:
            gallery_url = self.parse_url(css.get_attr(gallery_info, "href"))
            gallery_id = gallery_url.name
            scrape_item.album_id = gallery_id

        title: str = css.get_attr(image_tag, "alt")
        link = self.parse_url(css.get_attr(image_tag, "src"))
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(title, ext)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def is_cdn(url: AbsoluteHttpURL) -> bool:
    return "imagebam" in url.host.split(".") and "." in url.host.rstrip(".com")


def get_view_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    view_id = url.name.rsplit("_", 1)[0]
    return PRIMARY_URL / "view" / view_id
