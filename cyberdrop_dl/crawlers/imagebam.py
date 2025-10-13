from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
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


_SELECTORS = Selectors()
PRIMARY_URL = AbsoluteHttpURL("https://www.imagebam.com/")


class ImageBamCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Gallery": "/gallery/...",
        "Image": "/image/...",
        "Gallery or Image": "/view/...",
        "Thumbnails": "thumbs<x>.imagebam.com/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "imagebam"
    FOLDER_DOMAIN: ClassVar[str] = "ImageBam"
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE

    async def async_startup(self) -> None:
        # This skips the "Continue to image" pages.
        self.update_cookies({"nsfw_inter": "1"})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "thumbs" in scrape_item.url.host:
            scrape_item.url = thumbnail_to_img(scrape_item.url)
            # this is to update the URL in the UI
            # TODO: Add URL conversion methods as a pre_check step, before assigning them a task_id
            # Several crawlers do something like this
            self.create_task(self.run(scrape_item))
            return

        match scrape_item.url.parts[1:]:
            case ["gallery", _]:
                return await self.gallery(scrape_item)
            case ["image", _]:
                return await self.image(scrape_item)
            case ["view", _]:
                return await self.view(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def view(self, scrape_item: ScrapeItem) -> None:
        # view URLs can be either a gallery or a single image.
        soup = await self.request_soup(scrape_item.url)
        if soup.select_one(_SELECTORS.IS_GALLERY):
            return await self.gallery(scrape_item, soup)
        await self.image(scrape_item, soup)

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem, soup: BeautifulSoup | None = None) -> None:
        if not soup:
            soup = await self.request_soup(scrape_item.url)

        gallery_name = css.select_one_get_text(soup, _SELECTORS.GALLERY_TITLE)
        gallery_id = scrape_item.url.name
        title = self.create_title(gallery_name, gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)
        results = await self.get_album_results(gallery_id)

        def process_gallery_images(soup: BeautifulSoup) -> None:
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.THUMBNAILS):
                if not self.check_album_results(new_scrape_item.url, results):
                    self.create_task(self.image(new_scrape_item))

        process_gallery_images(soup)

        while next_page := css.select_one_get_attr_or_none(soup, _SELECTORS.NEXT_PAGE, "href"):
            soup = await self.request_soup(self.parse_url(next_page))
            process_gallery_images(soup)

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem, soup: BeautifulSoup | None = None) -> None:
        if not soup:
            if await self.check_complete_from_referer(scrape_item):
                return

            soup = await self.request_soup(scrape_item.url)

        image_tag = css.select_one(soup, _SELECTORS.IMAGE)
        if not scrape_item.album_id and (gallery_info := soup.select_one(_SELECTORS.GALLERY_INFO)):
            gallery_id = css.get_attr(gallery_info, "href").rsplit("/", 1)[-1]
            scrape_item.album_id = gallery_id

        title = css.get_attr(image_tag, "alt")
        link = self.parse_url(css.get_attr(image_tag, "src"))
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(title, ext)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def thumbnail_to_img(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    stem = Path(url.name).stem
    image_id = stem.removesuffix("_t")
    if image_id != stem:
        return PRIMARY_URL / "view" / image_id
    return PRIMARY_URL / "image" / image_id
