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

SupportedPaths = TypedDict(
    "SupportedPaths",
    {
        "Image": str | tuple[str, ...],
        "Direct Link": NotRequired[str | tuple[str, ...]],
        "Gallery": NotRequired[str | tuple[str, ...]],
    },
)


class GallerySelectors(NamedTuple):
    title: str
    images: str


class SimplePHPImageHostCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths]  # type: ignore[reportIncompatibleVariableOverride]
    IMG_SELECTOR = "div#container a img, div[class*=container] a img"
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
        album_id = self._get_id(scrape_item.url)

        if self.NEXT_PAGE_SELECTOR:
            web_pager = self._web_pager(scrape_item.url)
        else:
            web_pager = self._web_pager(scrape_item.url, lambda x: None)

        title: str = ""
        async for soup in web_pager:
            if not title:
                title = self.create_title(css.select_one_get_text(soup, self.GALLERY_SELECTORS.title), album_id)
                scrape_item.setup_as_album(title, album_id=album_id)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, self.GALLERY_SELECTORS.images):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:  # type: ignore[reportIncompatibleMethodOverride]
        if await self.check_complete_from_referer(scrape_item):
            return

        if scrape_item.url.name in ("noimage.php", "no_image.png"):
            raise ScrapeError(404)

        if self.HAS_CAPTCHA:
            data = self._prepare_post_data(scrape_item.url)
            get_soup = self.client.post_data_get_soup(self.DOMAIN, scrape_item.url, data=data)
        else:
            get_soup = self.client.get_soup(self.DOMAIN, scrape_item.url)

        async with self.request_limiter:
            soup = await get_soup

        soup_text = soup.get_text()
        if soup.select_one("[class*='message warn']") or "Image Removed or Bad Link" in soup_text:
            raise ScrapeError(410)

        if "This is a private gallery" in soup_text:
            raise ScrapeError(401, "Private gallery")

        await self._extract_img_from_page(scrape_item, soup)

    async def _extract_img_from_page(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        img = css.select_one(soup, self.IMG_SELECTOR)
        link = self.parse_url(css.get_attr(img, "src"))
        custom_filename = img.get("title") or img.get("alt") or link.name
        assert isinstance(custom_filename, str)
        custom_filename, ext = self.get_filename_and_ext(
            custom_filename.partition(" image hosted at")[0], assume_ext=".jpg"
        )
        await self.handle_file(link, scrape_item, link.name, ext, custom_filename=custom_filename)


class ImxToCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/i/<image_id>",
        "Direct Link": (
            "/u/t/<mm>/<dd>/<yyyy>/<image_id>",
            "/u/i/<mm>/<dd>/<yyyy>/<image_id>",
            "/i/<mm>/<dd>/<yyyy>/<image_id>",
            "/t/<mm>/<dd>/<yyyy>/<image_id>",
        ),
        "Gallery": "/g/<galery_id>",
    }
    GALLERY_SELECTORS = GallerySelectors("div.title", "div#content a:has(img)")
    PRIMARY_URL = AbsoluteHttpURL("https://imx.to")
    HAS_CAPTCHA = True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["g", _]:
                return await self.gallery(scrape_item)
            case ["i", _]:
                return await self.image(scrape_item)

        await ImgShotCrawler.fetch(self, scrape_item)

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL):
        match url.parts[1:]:
            case ["u" | "i" | "t", _, _, *_]:
                return cls._thumb_to_web_url(url)
            case _:
                return url

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = cls._get_id(url)
        return cls.PRIMARY_URL / "i" / image_id


class ImgAdultCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/img-<image_id>.html",
    }
    PRIMARY_URL = AbsoluteHttpURL("https://imgadult.com")
    HAS_CAPTCHA = True

    async def async_startup(self) -> None:
        self.update_cookies({"img_i_d": 1})


class AcidImgCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/i/<image_id>",
        "Direct Link": "/upload/...",
    }
    PRIMARY_URL = AbsoluteHttpURL("https://acidimg.cc")
    FOLDER_DOMAIN = "AcidImg"
    HAS_CAPTCHA = True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["g", _]:
                return await self.gallery(scrape_item)
            case ["i", _]:
                return await self.image(scrape_item)

        await ImgShotCrawler.fetch(self, scrape_item)

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL):
        match url.parts[1:]:
            case ["upload", "small" | "small-medium" | "big", _, *_]:
                return cls._thumb_to_web_url(url)
            case _:
                return url


class PicstateCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/view/full/<image_id>",
        "Direct Link": (
            "/files/<image_id>/<filename>",
            "/thumbs/small/files/<image_id>/<filename>",
        ),
    }
    PRIMARY_URL = AbsoluteHttpURL("https://picstate.com")
    IMG_SELECTOR = "p#image_container a img"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["view", "full", _]:
                return await self.image(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        match url.parts[1:]:
            case ["files" | "thumbs", _, _, *_]:
                return cls._thumb_to_web_url(url)
            case _:
                return url

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = url.parts[-2]
        return cls.PRIMARY_URL / "view/full" / image_id


class PixHostCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Gallery": "/gallery/<gallery_id>",
        "Image": "/show/<seq>/<filename>",
        "Direct Link": (
            "/thumbs/<seq>/<filename>",
            "/images/<seq>/<filename>",
        ),
    }
    PRIMARY_URL = AbsoluteHttpURL("https://pixhost.to/")
    GALLERY_SELECTORS = GallerySelectors(title="a.link h2", images="div.images a")
    IMG_SELECTOR = "img.image-img"
    DOMAIN = "pixhost"
    FOLDER_DOMAIN = "PixHost"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["gallery", _]:
                return await self.gallery(scrape_item)
            case ["show", _, _]:
                return await self.image(scrape_item)

        await ImgShotCrawler.fetch(self, scrape_item)

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL):
        match url.parts[1:]:
            case ["thumbs" | "images", _, _]:
                return cls._thumb_to_web_url(url)
            case _:
                return url

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        path = url.path.replace("/thumbs/", "/show/").replace("/images/", "/show/")
        return cls.PRIMARY_URL.with_path(path)


class ViprImCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/<image_id>",
        "Direct Link": (
            "/th/<seq>/<image_id>.<ext>",
            "/i/<seq>/<image_id>.<ext>/<filename>",
        ),
    }
    IMG_SELECTOR = "div#body a > img"
    PRIMARY_URL = AbsoluteHttpURL("https://vipr.im")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_]:
                return await self.image(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        match url.parts[1:]:
            case ["th" | "i", _, _, *_]:
                return cls._thumb_to_web_url(url)
            case _:
                return url

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = url.parts[3].rsplit(".", 1)[0]
        return cls.PRIMARY_URL / image_id


class ImageBamCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Image": (
            "/image/<image_id>",
            "/view/<id>",
        ),
        "Gallery": "/gallery/<image_id>",
        "Direct Link": (
            "thumbs<x>.imagebam.com/...",
            "images<x>.imagebam.com/...",
        ),
    }
    GALLERY_SELECTORS = GallerySelectors("a#gallery-name", "ul.images a.thumbnail")
    PRIMARY_URL = AbsoluteHttpURL("https://www.imagebam.com")
    DOMAIN = "imagebam"
    FOLDER_DOMAIN = "ImageBam"
    NEXT_PAGE_SELECTOR = "a.page-link[rel=next]"
    IMG_SELECTOR = "a .main-image"

    async def async_startup(self) -> None:
        self.update_cookies({"nsfw_inter": "1"})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["gallery", _]:
                return await self.gallery(scrape_item)
            case ["image", _]:
                return await self.image(scrape_item)
            case ["view", _]:
                return await self.view(scrape_item)
        raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        if "thumbs" in url.host or "images" in url.host:
            return cls._thumb_to_web_url(url)
        return url

    @error_handling_wrapper
    async def view(self, scrape_item: ScrapeItem) -> None:
        # view URLs can be either a gallery or a single image.
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        if soup.select_one(".card-header:contains('Share this gallery')"):
            return await self.gallery(scrape_item)
        await self.image(scrape_item)

    @classmethod
    def _get_id(cls, url: AbsoluteHttpURL) -> str:
        stem = url.name.rsplit(".", 1)[0]
        return stem.removesuffix("_t").removesuffix("_o")

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        stem = url.name.rsplit(".", 1)[0]
        image_id = cls._get_id(url)
        if image_id != stem:
            return cls.PRIMARY_URL / "view" / image_id
        return cls.PRIMARY_URL / "image" / image_id


class ImagetwistCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": (
            "/<image_id>.<ext>",
            "/<image_id>.<ext>/<filename>",
        ),
        "Direct Link": (
            "/th/<seq>/<image_id>.<ext>",
            "/i/<seq>/<image_id>.<ext>/<filename>",
        ),
    }
    PRIMARY_URL = AbsoluteHttpURL("https://imagetwist.com")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_]:
                return await self.image(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        match url.parts[1:]:
            case ["th" | "i", _, _, *_]:
                return cls._thumb_to_web_url(url)
            case [_, _]:
                return url.with_path(url.parts[1])
            case _:
                return url

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = url.parts[3].rsplit(".", 1)[0]
        return cls.PRIMARY_URL / image_id


class ImageVenueCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/<image_id>",
        "Direct Link": (
            "cdn-thumbs.imagevenue.com/<seq>/<seq>/<seq>/<filename>",
            "cdn-images.imagevenue.com/<seq>/<seq>/<seq>/<filename>",
        ),
    }
    PRIMARY_URL = AbsoluteHttpURL("https://www.imagevenue.com")
    IMG_SELECTOR = "a img#main-image"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_]:
                return await self.image(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        if len(url.parts) == 5 and ("thumbs" in url.host or "images" in url.host):
            return cls._thumb_to_web_url(url)
        return url

    @classmethod
    def _get_id(cls, url: AbsoluteHttpURL) -> str:
        stem = url.name.rsplit(".", 1)[0]
        return stem.removesuffix("_t").removesuffix("_o")

    @classmethod
    def _thumb_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = cls._get_id(url)
        return cls.PRIMARY_URL / image_id


__all__ = [
    name
    for name, crawler in globals().items()
    if name.endswith("Crawler") and crawler not in {Crawler, ImgShotCrawler, SimplePHPImageHostCrawler}
]  # type: ignore[reportUnsupportedDunderAll]
