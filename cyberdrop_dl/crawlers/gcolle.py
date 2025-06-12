from __future__ import annotations

import asyncio
import codecs
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from bs4 import BeautifulSoup
from pydantic import (
    AliasGenerator,
    BaseModel,
    ByteSize,
    ConfigDict,
    Field,
    PlainValidator,
    computed_field,
    field_validator,
)
from pydantic.alias_generators import to_camel

from cyberdrop_dl import constants
from cyberdrop_dl.crawlers._metadata import make_factory
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.models.types import StrSerializer
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper, parse_url

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterable

    from bs4 import Tag

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_categories_mapping: dict[int, Category] = {}


def _clean_img_url(url: AbsoluteHttpURL, part: str = "uploader") -> AbsoluteHttpURL:
    if part not in url.parts or url.suffix in constants.FILE_FORMATS["Videos"]:
        return url

    index = url.parts.index(part)
    filtered_path = "/".join(url.parts[index:])
    return url.with_path(filtered_path, keep_fragment=True, keep_query=True)


def _parse_gcolle_url(url_str: str) -> AbsoluteHttpURL:
    return _clean_img_url(parse_url(url_str, relative_to=PRIMARY_URL))


PRIMARY_URL = AbsoluteHttpURL("https://gcolle.net/")
IPHONE_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604"

GcolleHttpURL = Annotated[AbsoluteHttpURL, PlainValidator(_parse_gcolle_url), StrSerializer]

_ENCODING = "euc-jp"
_ERROR_DECODER = "euc-jp + utf-8"
_NO_BREAK_SPACE = b"\xad"
_3_BYTES_PREFIX = b"\xe2\x91"
_AGE_CHECK_EXPIRES_AFTER = timedelta(minutes=10)


def mixed_decoder(error: UnicodeError) -> tuple[str, int]:
    if isinstance(error, UnicodeDecodeError):
        content: bytes = error.object[error.start : error.end]
        if content == _NO_BREAK_SPACE:
            return " ", error.end
        if b"\xa0" <= content <= b"\xa9":
            try:
                return (_3_BYTES_PREFIX + content).decode("utf8"), error.end
            except UnicodeDecodeError:
                pass
        return content.decode("utf8", errors="backslashreplace"), error.end
    raise error


codecs.register_error(_ERROR_DECODER, mixed_decoder)


class GcolleURLPath:
    @staticmethod
    def category(joined_id: str) -> str:
        return f"default.php/cPath/{joined_id}"

    @staticmethod
    def seller(manufacturer_id: int | str) -> str:
        return f"default.php/manufacturers_id/{manufacturer_id}"

    @staticmethod
    def seller_videos(manufacturer_id: int | str, page_index: int = 1) -> str:
        return f"default.php/price/2/order/6d/manufacturers_id/{manufacturer_id}/page/{page_index}"

    @staticmethod
    def product(product_id: int | str) -> str:
        return f"product_info.php/products_id/{product_id}"

    @staticmethod
    def category_products(joined_id: str, page_index: int = 1) -> str:
        return f"default.php/cPath/{joined_id}/price/2/order/6d/page/{page_index}"

    @staticmethod
    def all_products(page_index: int = 1) -> str:
        return GcolleURLPath.category_products("254", page_index)


class SellerSelectors:
    name = "body h3"
    url = "form#filter"
    profile_image = "div.m-auto img"
    info_table = "div#info dl"


class ProductSelectors:
    categories = "a.btn-info:contains('Back to category')"
    contains = "tr:has(th:contains('Contains:')) td a"
    description = "div#description"
    info_table = "div.border-info table"
    main_section = "body > div.container"
    previews = "a[data-gallery='banners'] img"
    price = "p:has(span.fa-yen-sign)"
    tags = "p#tags a"
    video_preview = "video.video-js source"
    file_name = "tr:has(th:contains('File name:')) td"

    _file_size_row = "tr:has(th:contains('File size:'))"
    file_size = f"{_file_size_row} td"
    file_size_bytes = f"{_file_size_row} small.text-muted"

    _manufacturer = "div#manufacturer"
    _product_dt = "dt:contains('Products:')"
    trash = (
        "ul[role='tablist']",
        "div#questions p:contains('Ask a question')",
        "button:contains('Put into the cart')",
        f"{_manufacturer} span:contains('Consignor Data') + button[data-toggle=collapse]",
        f"{_manufacturer} ~ *",
        f"{_manufacturer} {_product_dt} ~ *",
        _product_dt,
    )


class Selectors:
    AGE_CHECK = "div#page-age-check"
    AGE_CHECK_LINK = "a.btn-danger"
    PRODUCT = ProductSelectors()
    CATEGORIES = "select[name='categories_id'] option"
    LD_JSON = "script[type='application/ld+json']:contains('@context')"
    PRODUCT_FROM_THUMB = "div.product-listing-item a.product-listing-name"
    NEXT_PAGE = "ul.pagination a.page-link:has(span.fa-angle-double-right)"
    SELLER = SellerSelectors()


DEFAULT_HEADERS = {
    "Accept-Language": "en-US,en",
    "Host": "gcolle.net",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Priority": "u=1",
}

_SELECTORS = Selectors()


class GcolleCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Direct links": "",
        "Category": "/default.php/cPath/<joined_id>",
        "Seller": "/default.php/manufacturers_id/<manufacturer_id>",
        "Product": "/product_info.php/products_id/<product_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "gcolle.net"
    NEXT_PAGE_SELECTOR = _SELECTORS.NEXT_PAGE

    def __post_init__(self) -> None:
        self.last_age_check: datetime | None = None
        self.age_check_lock = asyncio.Lock()
        self.product_sidecard_factory = make_factory(self, "product_info.json", GcolleProduct)
        self.product_html_sidecard_factory = make_factory(self, "product_info.html", str)
        self.seller_sidecard_factory = make_factory(self, "manufacturer_info.json", GcolleSeller)

    async def async_startup(self) -> None:
        await self.get_categories(PRIMARY_URL / GcolleURLPath.all_products())
        self.register_cache_filter(PRIMARY_URL, lambda _: True)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if not _categories_mapping:
            return
        if manufactured_id := _next_part(scrape_item.url, "manufacturers_id"):
            return await self.seller(scrape_item, manufactured_id)
        if products_id := _next_part(scrape_item.url, "products_id"):
            return await self.product(scrape_item, products_id)
        if (joined_id := _next_part(scrape_item.url, "cPath")) and (
            (joined_id := _fix_joined_id(joined_id)) in _categories_mapping
        ):
            return await self.category(scrape_item, joined_id)
        raise ValueError

    @error_handling_wrapper
    async def category(self, scrape_item: ScrapeItem, joined_id: str) -> None:
        init_page = int(_next_part(scrape_item.url, "page") or 1)
        scrape_item.url = PRIMARY_URL / GcolleURLPath.category(joined_id)
        scrape_item.setup_as_profile(self.create_title(f"{joined_id} [category]"))

        async for soup in self.web_pager(PRIMARY_URL / GcolleURLPath.category_products(joined_id, init_page)):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.PRODUCT_FROM_THUMB):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def seller(self, scrape_item: ScrapeItem, manufactured_id: str) -> None:
        init_page = int(_next_part(scrape_item.url, "page") or 1)
        scrape_item.url = PRIMARY_URL / GcolleURLPath.seller(manufactured_id)
        scrape_item.setup_as_profile(self.create_title(f"{manufactured_id} [seller]"))
        sidecard = self.seller_sidecard_factory(scrape_item)
        if content := await sidecard.read():
            seller = content
        else:
            soup = await self.get_soup_with_age_check(scrape_item.url)
            seller = parse_seller(soup)
            await sidecard.save(seller)

        if seller.profile_image:
            new_scrape_item = scrape_item.create_new(scrape_item.url, new_title_part="profile_image")
            await self.direct_file(new_scrape_item, seller.profile_image)

        async for soup in self.web_pager(PRIMARY_URL / GcolleURLPath.seller_videos(seller.id, init_page)):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.PRODUCT_FROM_THUMB):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def product(self, scrape_item: ScrapeItem, product_id: str) -> None:
        title = str(product_id)
        if not (parent := scrape_item.parent()) or PRIMARY_URL.host not in parent.host:  # type: ignore
            title = self.create_title(title)
        scrape_item.setup_as_album(title, album_id=product_id)
        scrape_item.url = PRIMARY_URL / GcolleURLPath.product(product_id)
        sidecard = self.product_sidecard_factory(scrape_item)
        if content := await sidecard.read():
            product = content
        else:
            soup = await self.get_soup_with_age_check(scrape_item.url)
            product = parse_product(soup)
            await sidecard.save(product)

        await self.product_html_sidecard_factory(scrape_item).save(product.html)
        scrape_item.possible_datetime = to_timestamp(product.date_published)
        new_scrape_item = scrape_item.create_new(scrape_item.url, new_title_part="previews")
        for preview_url in product.all_previews:
            await self.direct_file(new_scrape_item, preview_url)

    async def web_pager(self, url: AbsoluteHttpURL) -> AsyncGenerator[BeautifulSoup]:
        page_url = url
        while True:
            soup = await self.get_soup_with_age_check(page_url)
            yield soup
            page_url_str = css.select_one_get_attr_or_none(soup, self.NEXT_PAGE_SELECTOR, "href")
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str)

    async def get_soup_with_age_check(self, url: AbsoluteHttpURL) -> BeautifulSoup:
        soup = await self._get_soup(url)
        async with self.age_check_lock:
            if age_check := soup.select_one(_SELECTORS.AGE_CHECK):
                await self.client._session.cache.delete_url(url)
                if not self.last_age_check or (
                    ((now := datetime.now()) - self.last_age_check) > _AGE_CHECK_EXPIRES_AFTER
                ):
                    age_check_link = self.parse_url(
                        css.select_one_get_attr(age_check, _SELECTORS.AGE_CHECK_LINK, "href")
                    )
                    _ = await self.client._get(self.DOMAIN, age_check_link)
                    self.last_age_check = now
                soup = await self._get_soup(url)

        return soup

    async def _get_soup(self, url: AbsoluteHttpURL, mobile: bool = True) -> BeautifulSoup:
        """Forces euc-jp encoding"""
        if mobile:
            headers = DEFAULT_HEADERS | {"user-agent": IPHONE_USER_AGENT}
        else:
            headers = DEFAULT_HEADERS
        async with self.request_limiter:
            response, _ = await self.client._get(self.DOMAIN, url, headers, cache_disabled=not mobile)
            content = await response.read()
            text = _normalize(content.decode(_ENCODING, errors=_ERROR_DECODER))
            return BeautifulSoup(text, "html.parser")

    @error_handling_wrapper
    async def get_categories(self, url: AbsoluteHttpURL) -> None:
        global _categories_mapping
        if _categories_mapping:
            return

        # category list is only available on the desktop version of the site
        _ = await self.get_soup_with_age_check(url)
        soup = await self._get_soup(url, mobile=False)
        _categories_mapping = {cat.id: cat for cat in parse_categories(soup)}


@dataclass(frozen=True, slots=True, order=True)
class Category:
    id: int
    name: str
    joined_id: str


@dataclass(frozen=True, slots=True, order=True)
class Seller:
    id: int
    name: str


class GcolleModel(BaseModel):
    model_config = ConfigDict(alias_generator=AliasGenerator(validation_alias=to_camel))
    name: str
    url: GcolleHttpURL

    @computed_field
    @property
    def id(self) -> int:
        return int(self.url.name)


class GcolleProduct(GcolleModel):
    title: str
    file_name: str
    category: Category
    contains: list[int] = []
    date_created: datetime
    date_modified: datetime
    date_published: datetime
    description: str
    file_size: str  # approx, ex:: 1.4 GB
    file_size_bytes: ByteSize  # exact, from int, ex: 1_400_236, only the mobile version of the site has it
    headline: str
    previews: list[GcolleHttpURL] = []
    price: int
    seller: Seller = Field(validation_alias="author")
    tags: list[str] = Field([], validation_alias="keywords")
    tags_html: list[str]
    thumbnail: GcolleHttpURL = Field(validation_alias="image")
    video_preview: GcolleHttpURL | None = None
    html: str = Field(exclude=True)

    @field_validator("seller", mode="before")
    @classmethod
    def get_seller(cls, value: dict[str, str]) -> Seller:
        return Seller(int(value["url"].split("/")[-1]), value["name"])

    @field_validator("tags", mode="before")
    @classmethod
    def get_tags(cls, value: str) -> list[str]:
        return value.split(",")

    @property
    def all_previews(self) -> Generator[GcolleHttpURL]:
        if self.video_preview:
            yield self.video_preview
        yield from (self.thumbnail, *self.previews)


class GcolleSeller(GcolleModel):
    profile_image: GcolleHttpURL | None = None
    self_introduction: str | None = None
    email: str | None = None
    home_page: str | None = None
    action_area: str | None = None


def parse_seller(soup: BeautifulSoup) -> GcolleSeller:
    # Only works with soup from the MOBILE version of the site
    # The desktop version of the site is just several tables without speficic attributes or names
    seller: dict[str, str | None] = {
        "name": _normalize(css.select_one_get_text(soup, _SELECTORS.SELLER.name)),
        "url": css.select_one_get_attr(soup, _SELECTORS.SELLER.url, "action"),
    }

    if profile_image_tag := soup.select_one(_SELECTORS.SELLER.profile_image):
        seller["profile_image"] = css.get_attr(profile_image_tag, "src")

    if info_tag := soup.select_one(_SELECTORS.SELLER.info_table):
        info_dict = _dl_to_dict(info_tag)
        seller["email"] = info_dict.get("E Mail Address")
        seller["self_introduction"] = info_dict.get("Self Introduction")
        seller["home_page"] = info_dict.get("Home Page")
        seller["action_area"] = info_dict.get("Action Area")

    return GcolleSeller.model_validate(seller)


def parse_categories(soup: BeautifulSoup) -> Generator[Category]:
    # Only works with soup from the DESKTOP version of the site
    # Mobile version does not have any categories element
    current_parents: list[int | None] = [None, None, None]
    level_1_trash = ("├ ", "└ ")
    level_2_trash = tuple("│ " + char for char in level_1_trash)
    for category_tag in css.iselect(soup, _SELECTORS.CATEGORIES):
        n_of_parents = 0
        category_id = int(css.get_attr(category_tag, "value"))
        name = _normalize(category_tag.text)
        if any(trash in name for trash in level_2_trash):
            n_of_parents = 2

        elif any(trash in name for trash in level_1_trash):
            n_of_parents = 1

        current_parents[n_of_parents] = category_id

        for trash in (*level_1_trash, "│ "):
            name = name.replace(trash, "")

        joined_id = _fix_joined_id(x for x in current_parents[: n_of_parents + 1] if x is not None)
        yield Category(category_id, name.strip(), joined_id)


def parse_product(soup: BeautifulSoup) -> GcolleProduct:
    # Only works with soup from the MOBILE version of the site
    # The desktop version of the site is just several tables without speficic attributes or names
    product: dict[str, Any] = json.loads(_normalize(css.select_one_get_text(soup, _SELECTORS.LD_JSON)))
    main_section = css.select_one(soup, _SELECTORS.PRODUCT.main_section)
    info_table = css.select_one(main_section, _SELECTORS.PRODUCT.info_table)
    description_tag = css.select_one(main_section, _SELECTORS.PRODUCT.description)
    product["title"] = _normalize(css.select_one_get_text(main_section, "h1"))
    product["description"] = _normalize(description_tag.get_text(separator="\n").strip())

    del description_tag, soup

    joined_id = _fix_joined_id(css.select_one_get_attr(main_section, _SELECTORS.PRODUCT.categories, "href"))
    product["category"] = _categories_mapping[int(joined_id.split("_")[-1])]
    product["price"] = _digits(css.select_one_get_text(main_section, _SELECTORS.PRODUCT.price))
    product["tags_html"] = [_normalize(css.get_text(tag)) for tag in main_section.select(_SELECTORS.PRODUCT.tags)]
    product["file_name"] = css.select_one_get_text(info_table, _SELECTORS.PRODUCT.file_name)
    product["file_size_bytes"] = _digits(css.select_one_get_text(info_table, _SELECTORS.PRODUCT.file_size_bytes))
    product["file_size"] = (
        css.select_one_get_text(info_table, _SELECTORS.PRODUCT.file_size)
        .replace("Total", "")
        .strip()
        .split("\n")[0]
        .split("(")[0]
        .strip()
    )
    product["previews"] = [css.get_attr(preview, "src") for preview in main_section.select(_SELECTORS.PRODUCT.previews)]
    product["contains"] = [
        int(css.get_attr(item, "href").split("/")[-1]) for item in info_table.select(_SELECTORS.PRODUCT.contains)
    ]
    if video_preview_tag := main_section.select_one(_SELECTORS.PRODUCT.video_preview):
        product["video_preview"] = css.get_attr(video_preview_tag, "src")

    get_clean_html(main_section)
    product["html"] = _normalize(main_section.prettify())
    return GcolleProduct.model_validate(product, by_alias=True, by_name=True)


def _next_part(url: AbsoluteHttpURL, part: str) -> str | None:
    try:
        return url.parts[url.parts.index(part) + 1]
    except (IndexError, ValueError):
        return


def _fix_joined_id(joined_id: Iterable[int] | str) -> str:
    if isinstance(joined_id, str):
        id_list = joined_id.split("/")[-1].split("_")
    else:
        id_list = map(str, joined_id)

    return "_".join(sorted(id_list, key=int))


def _digits(string: str) -> int:
    return int(re.sub(r"\D", "", string).strip())


def _dl_to_dict(html_content: Tag) -> dict[str, str]:
    return {
        _normalize(css.get_text(dt)): _normalize(css.get_text(dd))
        for dt, dd in zip(css.iselect(html_content, "dt"), css.iselect(html_content, "dd"), strict=False)
    }


def _normalize(string: str) -> str:
    return unicodedata.normalize("NFKC", string)


def get_clean_html(main_section: Tag) -> None:
    for selector in _SELECTORS.PRODUCT.trash:
        for trash in css.iselect(main_section, selector):
            trash.decompose()

    make_links_absolute(main_section)


def make_links_absolute(tag: Tag) -> None:
    for attr in ("href", "src", "data-src"):
        for inner_tag in css.iselect(tag, f"[{attr}^='/']"):
            try:
                inner_tag[attr] = str(_parse_gcolle_url(css.get_attr(inner_tag, attr)))
            except Exception:
                continue
