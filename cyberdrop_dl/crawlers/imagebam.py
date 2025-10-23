from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    GALLERY_TITLE = "a#gallery-name"
    THUMBNAILS = "ul.images a.thumbnail"
    IMAGE = "img.main-image"
    GALLERY_INFO = "div.view-navigation a:has(i.fas.fa-reply)"
    IS_GALLERY = ".card-header:-soup-contains('Share this gallery')"
    NEXT_PAGE = "a.page-link[rel=next]"


_PRIMARY_URL = AbsoluteHttpURL("https://www.imagebam.com/")


class ImageBamCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Gallery": "/gallery/<id>",
        "Image": (
            "/image/<id>",
            "images<x>.imagebam.com/<id>",
        ),
        "Gallery or Image": "/view/<id>",
        "Thumbnails": "thumbs<x>.imagebam.com/<id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "imagebam"
    FOLDER_DOMAIN: ClassVar[str] = "ImageBam"
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selectors.NEXT_PAGE

    async def async_startup(self) -> None:
        # This skips the "Continue to image" pages.
        self.update_cookies({"nsfw_inter": "1", "sfw_inter": "1"})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["gallery", _]:
                return await self.gallery(scrape_item)
            case ["image", _]:
                return await self.image(scrape_item)
            case ["view", _]:
                return await self.view(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        if cls.is_subdomain(url):
            return thumbnail_to_img(url)
        return url

    @error_handling_wrapper
    async def view(self, scrape_item: ScrapeItem) -> None:
        # view URLs can be either a gallery or a single image.
        soup = await self.request_soup(scrape_item.url)
        if soup.select_one(Selectors.IS_GALLERY):
            return await self.gallery(scrape_item, soup)
        await self.image(scrape_item, soup)

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem, soup: BeautifulSoup | None = None) -> None:
        if not soup:
            soup = await self.request_soup(scrape_item.url)

        gallery_name = css.select_one_get_text(soup, Selectors.GALLERY_TITLE)
        gallery_id = scrape_item.url.name
        title = self.create_title(gallery_name, gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)
        results = await self.get_album_results(gallery_id)

        while True:
            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selectors.THUMBNAILS, results=results):
                self.create_task(self._image_task(new_scrape_item))

            next_page = css.select_one_get_attr_or_none(soup, Selectors.NEXT_PAGE, "href")
            if not next_page:
                break
            soup = await self.request_soup(self.parse_url(next_page))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem, soup: BeautifulSoup | None = None) -> None:
        if not soup:
            if await self.check_complete_from_referer(scrape_item):
                return

            soup = await self.request_soup(scrape_item.url)

        image_tag = css.select_one(soup, Selectors.IMAGE)
        if not scrape_item.album_id and (gallery_info := soup.select_one(Selectors.GALLERY_INFO)):
            gallery_id = self.parse_url(css.get_attr(gallery_info, "href")).name
            scrape_item.album_id = gallery_id

        title = css.get_attr(image_tag, "alt")
        link = self.parse_url(css.get_attr(image_tag, "src"))
        custom_filename, ext = self.get_filename_and_ext(title)
        await self.handle_file(link, scrape_item, link.name, ext, custom_filename=custom_filename)

    _image_task = auto_task_id(image)


def thumbnail_to_img(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    stem = Path(url.name).stem
    image_id = stem.removesuffix("_t").removesuffix("_o")
    if image_id != stem:
        return _PRIMARY_URL / "view" / image_id
    return _PRIMARY_URL / "image" / image_id
