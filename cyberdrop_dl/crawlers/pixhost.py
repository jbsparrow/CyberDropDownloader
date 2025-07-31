from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    GALLERY_TITLE = "a.link h2"
    GALLERY_IMAGES = "div.images a"
    IMAGE = "img.image-img"


_SELECTORS = Selectors()
PRIMARY_URL = AbsoluteHttpURL("https://pixhost.to/")


class PixHostCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Gallery": "/gallery/<gallery_id>",
        "Image": "/show/<image_id>",
        "Thumbnail": "/thumbs/..",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    UPDATE_UNSUPPORTED: ClassVar[bool] = True
    DOMAIN: ClassVar[str] = "pixhost"
    FOLDER_DOMAIN: ClassVar[str] = "PixHost"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if self.is_thumbnail(scrape_item.url):
            src = _thumbnail_to_src(scrape_item.url)
            scrape_item.url = _thumbnail_to_web_url(scrape_item.url)
            return await self.direct_file(scrape_item, src)

        match scrape_item.url.parts[1:]:
            case ["gallery", gallery_id]:
                return await self.gallery(scrape_item, gallery_id)
            case ["show", _]:
                return await self.image(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem, album_id: str) -> None:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        title = css.select_one_get_text(soup, _SELECTORS.GALLERY_TITLE)
        title = self.create_title(title, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        results = await self.get_album_results(album_id)

        for thumb, web_url in self.iter_tags(soup, _SELECTORS.GALLERY_IMAGES):
            assert thumb
            src = _thumbnail_to_src(thumb)
            if not self.check_album_results(src, results):
                new_scrape_item = scrape_item.create_child(web_url)
                self.create_task(self.direct_file(new_scrape_item, src))
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str = css.select_one_get_attr(soup, _SELECTORS.IMAGE, "src")
        link = self.parse_url(link_str)
        await self.direct_file(scrape_item, link)

    @classmethod
    def is_thumbnail(cls, url: AbsoluteHttpURL):
        return "thumbs" in url.parts and cls.is_subdomain(url)


def _thumbnail_to_src(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    # https://t100.pixhost.to/thumbs/491/538303440_005.jpg -> https://img100.pixhost.to/images/491/538303440_005.jpg
    thumb_server_id = url.host.split(".", 1)[0].split("t")[-1]
    img_host = f"img{thumb_server_id}.{PRIMARY_URL.host}"
    new_path = url.path.replace("/thumbs/", "/images/")
    return url.with_host(img_host).with_path(new_path)


def _thumbnail_to_web_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    new_path = url.path.replace("/thumbs/", "/show/")
    return url.with_host(PRIMARY_URL.host).with_path(new_path)
