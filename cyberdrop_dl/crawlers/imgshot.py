"""Crawlers for image host sites that use simple php scripts"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar, NamedTuple, NotRequired, TypedDict

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class GallerySelectors(NamedTuple):
    title: str
    images: str


class SupportedPaths(TypedDict):
    Image: str
    Thumbnail: str
    Gallery: NotRequired[str]


class SimplePHPImageHostCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths]  # type: ignore[reportIncompatibleVariableOverride]
    IMG_SELECTOR: ClassVar[str] = "div#container a img"
    GALLERY_SELECTORS: GallerySelectors

    def __init_subclass__(cls, is_abc: bool = False, **kwargs) -> None:
        if not is_abc:
            if not getattr(cls, "DOMAIN", None) or cls.DOMAIN.casefold() not in cls.PRIMARY_URL.host:
                cls.DOMAIN = cls.PRIMARY_URL.host

            if not getattr(cls, "FOLDER_DOMAIN", None) or cls.FOLDER_DOMAIN.casefold() not in cls.PRIMARY_URL.host:
                cls.FOLDER_DOMAIN = cls.DOMAIN.capitalize()

            if "Gallery" in cls.SUPPORTED_PATHS:
                assert getattr(cls, "GALLERY_SELECTORS", None)

        super().__init_subclass__(is_abc=is_abc, **kwargs)

    @property
    def allow_no_extension(self):  # type: ignore[reportIncompatibleMethodOverride]
        return True

    @classmethod
    def _get_id(cls, url: AbsoluteHttpURL) -> str:
        return url.name.removeprefix("img-").partition(".")[0]

    async def direct_image(self, scrape_item: ScrapeItem) -> None:
        # convert the direct file to a wb page URL
        # we can convert it to an original src URL, but it will be missing the proper filename
        scrape_item.url = self._thumb_to_web_url(scrape_item.url)
        self.create_task(self.run(scrape_item))

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = cls._get_id(url)
        return cls.PRIMARY_URL / f"img-{image_id}.html"

    @abstractmethod
    async def image(self, scrape_item: ScrapeItem) -> None: ...

    @abstractmethod
    async def gallery(self, scrape_item: ScrapeItem) -> None: ...


class ImgShotCrawler(SimplePHPImageHostCrawler, is_abc=True):
    """Base crawler for websites that use the imgshot php script or something similar

    https://web.archive.org/web/20201129073840/https://codecanyon.net/item/imgshot-image-hosting-script/2558257
    https://web.archive.org/web/20140616140702/http://documentation.imgshot.com/
    """

    HAS_CAPTCHA: ClassVar[bool] = False

    async def async_startup(self) -> None:
        self.update_cookies({"continue": 1})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [name] if name.startswith("img-"):
                return await self.image(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def _prepare_post_data(cls, url: AbsoluteHttpURL) -> dict[str, str]:
        return {"imgContinue": "Continue+to+image+...+"}

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:  # type: ignore[reportIncompatibleMethodOverride]
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        album_id = self._get_id(scrape_item.url)
        title = self.create_title(css.select_one_get_text(soup, self.GALLERY_SELECTORS.title))
        scrape_item.setup_as_album(title, album_id=album_id)

        for _, new_scrape_item in self.iter_children(scrape_item, soup, self.GALLERY_SELECTORS.images):
            self.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:  # type: ignore[reportIncompatibleMethodOverride]
        if await self.check_complete_from_referer(scrape_item):
            return

        if scrape_item.url.name in "noimage.php":
            raise ScrapeError(404)

        if self.HAS_CAPTCHA:
            data = self._prepare_post_data(scrape_item.url)
            get_soup = self.client.post_data_get_soup(self.DOMAIN, scrape_item.url, data=data)
        else:
            get_soup = self.client.get_soup(self.DOMAIN, scrape_item.url)

        async with self.request_limiter:
            soup = await get_soup

        await self._process_img_soup(scrape_item, soup)

    async def _process_img_soup(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        soup_text = soup.get_text()
        if soup.select_one("[class*='message warn']") or "Image Removed or Bad Link" in soup_text:
            raise ScrapeError(410)

        if "This is a private gallery" in soup_text:
            raise ScrapeError(401, "Private gallery")

        img = css.select_one(soup, self.IMG_SELECTOR)
        link = self.parse_url(css.get_attr(img, "src"))
        name = css.get_attr_or_none(img, "title") or css.get_attr_or_none(img, "alt") or link.name
        filename, ext = self.get_filename_and_ext(name, assume_ext=".jpg")
        await self.handle_file(link, scrape_item, filename, ext)


class ImxToCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/i/...",
        "Thumbnail": "/u/t...",
        "Gallery": "/g/galery_id",
    }
    GALLERY_SELECTORS = GallerySelectors("div.title", "div#content a:has(img)")
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://imx.to")
    IMG_SELECTOR = "div#container div a img.centred"
    HAS_CAPTCHA = True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["g", _]:
                return await self.gallery(scrape_item)
            case ["u", "t" | "i", _, *_]:
                return await self.direct_image(scrape_item)
            case ["i", _]:
                return await self.image(scrape_item)
            case ["i", _, _, *_]:
                return await self.direct_image(scrape_item)
            case [name] if name.startswith("img-"):
                return await self.image(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = cls._get_id(url)
        return cls.PRIMARY_URL / "i" / image_id


class AcidImgCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/i/...",
        "Thumbnail": "/upload/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://acidimg.cc")
    FOLDER_DOMAIN: ClassVar[str] = "AcidImg"
    HAS_CAPTCHA = True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["g", _]:
                return await self.gallery(scrape_item)
            case ["upload", "small" | "small-medium" | "big", _, *_]:
                return await self.direct_image(scrape_item)
            case ["i", _]:
                return await self.image(scrape_item)
        await ImgShotCrawler.fetch(self, scrape_item)


class ImgAdultCrawler(AcidImgCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://imgadult.com")


class FappicCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/<image_id>/<filename>",
        "Thumbnail": "/upload/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://fappic.com")
    IMG_SELECTOR = "img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["upload", "thumbs" | "images", _, *_]:
                return await self.direct_image(scrape_item)
            case [_, _]:
                return await self.image(scrape_item)
        await ImgShotCrawler.fetch(self, scrape_item)


class PicstateCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/view/full/...",
        "Thumbnail": "/files/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://picstate.com")
    IMG_SELECTOR = "img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["files", _, *_]:
                return await self.direct_image(scrape_item)
            case ["view", "full", _]:
                return await self.image(scrape_item)

        await ImgShotCrawler.fetch(self, scrape_item)


class ViprImageCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/<image_id>.html",
        "Thumbnail": "/th/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://vipr2.im")
    IMG_SELECTOR = "img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["th", _]:
                return await self.direct_image(scrape_item)
            case [_]:
                return await self.image(scrape_item)

        await ImgShotCrawler.fetch(self, scrape_item)


class ImgClickCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/<image_id>/<filename>",
        "Thumbnail": "/thumbs/",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://imgclick.net")
    IMG_SELECTOR = "img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["upload", "thumbs" | "images", _, *_]:
                return await self.direct_image(scrape_item)
            case [_, _]:
                return await self.image(scrape_item)
        await ImgShotCrawler.fetch(self, scrape_item)

    @classmethod
    def _prepare_post_data(cls, url: AbsoluteHttpURL) -> dict[str, str]:
        return {
            "op": "view",
            "id": cls._get_id(url),
            "pre": "1",
            "adb": "1",
            "next": "Continue+to+image+...+",
        }


class PixHostCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Gallery": "/gallery/<gallery_id>",
        "Image": "/show/...",
        "Thumbnail": "/thumbs/..",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://pixhost.to/")
    GALLERY_SELECTORS = GallerySelectors(title="a.link h2", images="div.images a")
    IMG_SELECTOR = "img.image-img"
    DOMAIN: ClassVar[str] = "pixhost"
    FOLDER_DOMAIN: ClassVar[str] = "PixHost"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["gallery", _]:
                return await self.gallery(scrape_item)
            case ["thumbs" | "images", _, *_]:
                return await self.direct_image(scrape_item)
            case ["show", _, *_]:
                return await self.image(scrape_item)
        await ImgShotCrawler.fetch(self, scrape_item)

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        path = url.path.replace("/thumbs/", "/show/")
        return url.with_host(cls.PRIMARY_URL.host).with_path(path)


__all__ = [
    name
    for name, crawler in globals().items()
    if name.endswith("Crawler") and crawler not in {Crawler, ImgShotCrawler, SimplePHPImageHostCrawler}
]  # type: ignore[reportUnsupportedDunderAll]
