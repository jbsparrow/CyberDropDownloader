"""Crawlers for image host sites that use simple php scripts"""

from __future__ import annotations

import re
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


class Paths(NamedTuple):
    image: str
    thumbnail: str
    gallery: str | None = None


class SupportedPaths(TypedDict):
    Image: str
    Thumbnail: str
    Gallery: NotRequired[str]


class SimplePHPImageHostCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths]  # type: ignore[reportIncompatibleVariableOverride]
    IMG_SELECTOR: ClassVar[str] = "div#container a img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, ...]]
    GALLERY_SELECTORS: GallerySelectors
    MATCH_IMG_PATH_BY_LEN = 0

    def __init_subclass__(cls, is_abc: bool = False, **kwargs) -> None:
        if not is_abc:
            if not getattr(cls, "DOMAIN", None):
                cls.DOMAIN = cls.PRIMARY_URL.host

            cls.PATHS = Paths(**{k.lower(): v.removesuffix("...") for k, v in cls.SUPPORTED_PATHS.items() if v})
            if cls.PATHS.gallery:
                assert hasattr(cls, "GALLERY_SELECTORS")

            *thumb_paths, src_path = cls.THUMB_TO_SRC_REPLACE
            cls.THUMB_TO_SRC_REGEX = re.compile("|".join(thumb_paths))
        super().__init_subclass__(is_abc=is_abc, **kwargs)

    @property
    def allow_no_extension(self):  # type: ignore[reportIncompatibleMethodOverride]
        return True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        img, thumb, gallery = self.PATHS
        if gallery and gallery in scrape_item.url.path:
            return await self.gallery(scrape_item)
        if thumb in scrape_item.url.path:
            return await self.thumbnail(scrape_item)
        if self.MATCH_IMG_PATH_BY_LEN:
            if len(scrape_item.url.parts) == self.MATCH_IMG_PATH_BY_LEN:
                return await self.image(scrape_item)
        elif img in scrape_item.url.path:
            return await self.image(scrape_item)
        raise ValueError

    @classmethod
    def _get_id(cls, url: AbsoluteHttpURL) -> str:
        name = url.parts[2] if cls.PATHS.image.startswith("/<image_id>") else url.name
        return name.removeprefix("img-").removesuffix(".html")

    async def thumbnail(self, scrape_item: ScrapeItem) -> None:
        src = self._thumb_to_src(scrape_item.url)
        scrape_item.url = self._src_to_web_url(src)
        await self.direct_file(scrape_item, src, assume_ext=".jpg")

    @classmethod
    def _thumb_to_src(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        thumb_host = url.host.partition(cls.PRIMARY_URL.host)[0]
        img_host = f"{thumb_host.replace('t', 'img')}{cls.PRIMARY_URL.host}"
        src_path_prefix = cls.THUMB_TO_SRC_REPLACE[-1]
        src_path = cls.THUMB_TO_SRC_REGEX.sub(src_path_prefix, url.path)
        return url.with_host(img_host).with_path(src_path)

    @classmethod
    def _src_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
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
        results = await self.get_album_results(album_id)

        for thumb, web_url in self.iter_tags(soup, self.GALLERY_SELECTORS.images):
            assert thumb
            src = self._thumb_to_src(thumb)
            if not self.check_album_results(src, results):
                new_scrape_item = scrape_item.create_child(web_url)
                self.create_task(self.direct_file(new_scrape_item, src, assume_ext=".jpg"))
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:  # type: ignore[reportIncompatibleMethodOverride]
        if await self.check_complete_from_referer(scrape_item):
            return

        if scrape_item.url.name == "noimage.php":
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
        if soup.select_one("[class*='message warn']") or "Image Removed or Bad Link" in soup.text:
            raise ScrapeError(410)

        img = css.select_one(soup, self.IMG_SELECTOR)
        link = self.parse_url(css.get_attr(img, "src"))
        name = css.get_attr_or_none(img, "title") or css.get_attr_or_none(img, "alt") or link.name
        filename, ext = self.get_filename_and_ext(name, assume_ext=".jpg")
        await self.handle_file(link, scrape_item, filename, ext)


class ImxToCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/i/...",
        "Thumbnail": "/t/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://imx.to")
    THUMB_TO_SRC_REPLACE = "u/t", "u/i"
    IMG_SELECTOR = "div#container div a img.centred"
    HAS_CAPTCHA = True

    @classmethod
    def _src_to_web_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = cls._get_id(url)
        return cls.PRIMARY_URL / "i" / image_id


class AcidImgCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/i/...",
        "Thumbnail": "/upload/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://acidimg.cc")
    FOLDER_DOMAIN: ClassVar[str] = "AcidImg"
    THUMB_TO_SRC_REPLACE = "/upload/small/", "/upload/small-medium/", "/upload/big/"
    HAS_CAPTCHA = True


class ImgAdultCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/i/...",
        "Thumbnail": "/upload/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://imgadult.com")
    THUMB_TO_SRC_REPLACE = "/upload/small/", "/upload/small-medium/", "/upload/big/"
    HAS_CAPTCHA = True


class FappicCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/<image_id>/<filename>",
        "Thumbnail": "/upload/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://fappic.com")
    IMG_SELECTOR = "img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"


class PicstateCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/view/full/...",
        "Thumbnail": "/files/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://picstate.com")
    IMG_SELECTOR = "img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"


class ViprImageCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/<image_id>.html",
        "Thumbnail": "/th/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://vipr2.im")
    IMG_SELECTOR = "img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"
    MATCH_IMG_PATH_BY_LEN = 2


class ImgClickCrawler(ImgShotCrawler):
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/<image_id>/<filename>",
        "Thumbnail": "/thumbs/",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://imgclick.net")
    IMG_SELECTOR = "img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"
    MATCH_IMG_PATH_BY_LEN = 3

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
    SUPPORTED_PATHS: ClassVar = {
        "Image": "/show/",
        "Thumbnail": "/thumbs/",
        "Gallery": "/gallery/",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://pixhost.to/")
    GALLERY_SELECTORS = GallerySelectors(title="a.link h2", images="div.images a")
    IMG_SELECTOR = "img.image-img"
    THUMB_TO_SRC_REPLACE: ClassVar[tuple[str, str]] = "/thumbs/", "/images/"
    DOMAIN: ClassVar[str] = "pixhost"
    FOLDER_DOMAIN: ClassVar[str] = "PixHost"


__all__ = [
    name
    for name, crawler in globals().items()
    if name.endswith("Crawler") and crawler not in {Crawler, ImgShotCrawler, SimplePHPImageHostCrawler}
]  # type: ignore[reportUnsupportedDunderAll]
