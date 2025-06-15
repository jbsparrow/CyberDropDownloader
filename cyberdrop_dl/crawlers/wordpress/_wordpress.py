"""General crawler for all wordpress sites

Reference: https://developer.wordpress.org/rest-api/reference/#rest-api-developer-endpoint-reference
"""

from __future__ import annotations

import datetime
import itertools
import re
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, TypeVar, final

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from pydantic import BaseModel

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from .models import Category, CategorySequence, ColletionType, Html, Post, PostSequence, Tag, TagSequence

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterable, Callable, Iterable

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


_POST_PER_REQUEST = 100

_T = TypeVar("_T")
_ModelT = TypeVar("_ModelT", bound=BaseModel)
_HTTP_URL_REGEX = re.compile(
    r"https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,12}\b([-a-zA-Z0-9@:%_+.~#?&/=]*)"
)  # Same as Xenforo
_1_day = datetime.timedelta(days=1)


class DateRange(NamedTuple):
    before: datetime.datetime | None = None
    after: datetime.datetime | None = None

    @staticmethod
    def from_url(url: AbsoluteHttpURL) -> DateRange | None:
        self = DateRange(_date_from_query_param(url, "before"), _date_from_query_param(url, "after"))
        if self == (None, None):
            return None
        if (self.before and self.after) and (self.before <= self.after):
            raise ValueError
        return self

    def as_query(self) -> dict[str, Any]:
        return {name: value.isoformat() for name, value in self._asdict().items() if value}


class WordPressBaseCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Category": "/category/<category_slug>",
        "Tag": "/tag/<tag_slug>",
        "Post": "/<post_slug>/",
        "All Posts": "/posts/",
        "Date Range": (
            "...?before=<date>",
            "...?after=<date>",
            "...?before=<date&after=<date>",
        ),
        "**NOTE**": """

        For `Date Range`, <date>  must be a valid iso 8601 date, ex: `2022-12-06`.

        `Date Range` can be combined with `Category`, `Tag` and `All Posts`.
        ex: To only download categories from a date range: ,
        `/category/<category_slug>?before=<date>`""",
    }
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date} - {id} - {title}"
    WP_USE_REGEX: ClassVar = True

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        assert cls.fetch is WordPressBaseCrawler.fetch
        assert cls.fetch_with_date_range is WordPressBaseCrawler.fetch_with_date_range

    @final
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        date_range = DateRange.from_url(scrape_item.url)
        scrape_item.url = scrape_item.url.with_query(None)
        if date_range:
            self.log(f"Scraping {scrape_item.url} with date range: {date_range.as_query()}")
        return await self.fetch_with_date_range(scrape_item, date_range)

    @property
    def separate_posts(self) -> bool:
        # For wordpress we should always create a separate folder. Each post is an individual page
        return True

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(3, 1)

    @staticmethod
    def is_attachment(url: AbsoluteHttpURL) -> bool:
        return "wp-content" in url.parts and bool(url.suffix)

    @classmethod
    def is_self_attachment(cls, url: AbsoluteHttpURL) -> bool:
        return cls.is_attachment(url) and url.host == cls.PRIMARY_URL.host

    @final
    async def fetch_with_date_range(self, scrape_item: ScrapeItem, date_range: DateRange | None) -> None:
        match scrape_item.url.parts[1:3]:
            case ["posts"]:
                return await self.all_posts(scrape_item, date_range)
            case [ColletionType.CATEGORY.value, _]:
                return await self.category_or_tag(scrape_item, ColletionType.CATEGORY, date_range)
            case [ColletionType.TAG.value, _]:
                return await self.category_or_tag(scrape_item, ColletionType.TAG, date_range)
            case _:
                return await self.post(scrape_item)

    @abstractmethod
    async def category_or_tag(
        self, scrape_item: ScrapeItem, colletion_type: ColletionType, date_range: DateRange | None = None
    ) -> None: ...

    @abstractmethod
    async def post(self, scrape_item: ScrapeItem) -> None: ...

    @abstractmethod
    async def all_posts(self, scrape_item: ScrapeItem, date_range: DateRange | None = None) -> None: ...

    @abstractmethod
    async def post_pager(self, api_url: AbsoluteHttpURL) -> AsyncGenerator[Post]: ...

    def extract_links(self, html: Html) -> Iterable[AbsoluteHttpURL]:
        soup = BeautifulSoup(html, "html.parser")
        images = (link for _, link in self.iter_tags(soup, "img", "src"))
        iframes = (link for _, link in self.iter_tags(soup, "iframe", "data-src"))

        def regex_links() -> Iterable[AbsoluteHttpURL]:
            if not self.WP_USE_REGEX:
                return
            for link_str in unique(match.group() for match in re.finditer(_HTTP_URL_REGEX, html)):
                try:
                    yield self.parse_url(link_str)
                except Exception:
                    continue

        return unique(itertools.chain(images, iframes, regex_links()))

    def parse_url(self, link: str) -> AbsoluteHttpURL:
        # TODO: handle more domains and move it to the base crawler
        url = super().parse_url(link)
        if url.host == "ouo.io" and (redirect_url := url.query.get("s")):
            return super().parse_url(redirect_url)
        return url

    @final
    async def handle_post(self, scrape_item: ScrapeItem, post: Post, *, is_single_post: bool = False) -> None:
        post_id = str(post.id)
        title = self.create_separate_post_title(post.title, post_id, post.date_gmt.date())
        if is_single_post:
            title = self.create_title(title)
        scrape_item.setup_as_album(title, album_id=post_id)
        scrape_item.possible_datetime = to_timestamp(post.date)
        if post.thumbnail:
            await self.direct_file(scrape_item, self.parse_url(post.thumbnail))
        return await self.handle_post_content(scrape_item, post.content)

    async def handle_post_content(self, scrape_item: ScrapeItem, html: Html) -> None:
        for link in self.extract_links(html):
            await self.handle_link(scrape_item, link)

    @final
    async def handle_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL) -> None:
        if self.is_self_attachment(link):
            return await self.direct_file(scrape_item, link)
        if self.PRIMARY_URL.host == link.host:
            return
        new_scrape_item = scrape_item.create_new(link)
        new_scrape_item.type = None
        new_scrape_item.reset_childen()
        self.handle_external_links(new_scrape_item)
        scrape_item.add_children()

    @final
    async def iter_posts(self, scrape_item: ScrapeItem, api_url: AbsoluteHttpURL) -> None:
        async for post in self.post_pager(api_url):  # type: ignore
            new_scrape_item = scrape_item.create_child(self.parse_url(post.link))
            await self.handle_post(new_scrape_item, post)
            scrape_item.add_children()


class WordPressAPICrawler(WordPressBaseCrawler, is_abc=True):
    WP_CATEGORIES_ENDPOINT: ClassVar = "/wp-json/wp/v2/categories"
    WP_TAGS_ENDPOINT: ClassVar = "/wp-json/wp/v2/tags"
    WP_POSTS_ENDPOINT: ClassVar = "/wp-json/wp/v2/posts"

    def __init_subclass__(cls, is_abc: bool = False, **kwargs) -> None:
        super().__init_subclass__(is_abc=is_abc, **kwargs)
        if is_abc:
            return
        cls.CATEGORIES_URL = cls.PRIMARY_URL / cls.WP_CATEGORIES_ENDPOINT.removeprefix("/")
        cls.TAGS_URL = cls.PRIMARY_URL / cls.WP_TAGS_ENDPOINT.removeprefix("/")
        cls.POSTS_URL = cls.PRIMARY_URL / cls.WP_POSTS_ENDPOINT.removeprefix("/")

    async def __make_request(self, model_cls: type[_ModelT], api_url: AbsoluteHttpURL) -> _ModelT:
        async with self.request_limiter:
            json_text = await self.client.get_text(self.DOMAIN, api_url)
        return model_cls.model_validate_json(json_text)

    @error_handling_wrapper
    async def category_or_tag(
        self, scrape_item: ScrapeItem, colletion_type: ColletionType, date_range: DateRange | None = None
    ) -> None:
        if colletion_type is ColletionType.CATEGORY:
            model, api_url = CategorySequence, self.CATEGORIES_URL.with_query(slug=scrape_item.url.name)
        elif colletion_type is ColletionType.TAG:
            model, api_url = TagSequence, self.TAGS_URL.with_query(slug=scrape_item.url.name)

        collections = await self.__make_request(model, api_url)
        if not collections:
            raise ScrapeError(404)
        await self.handle_collection(scrape_item, collections[0], date_range)

    async def handle_collection(
        self, scrape_item: ScrapeItem, collection: Category | Tag, date_range: DateRange | None = None
    ) -> None:
        title = self.create_title(f"{collection.description or collection.slug} [{collection._type}]")
        scrape_item.setup_as_profile(title)
        api_url = self.POSTS_URL.with_query({collection._type: collection.id})
        if date_range:
            api_url = api_url.update_query(date_range.as_query())
        await self.iter_posts(scrape_item, api_url)

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        posts = await self.__make_request(PostSequence, self.POSTS_URL.with_query(slug=scrape_item.url.name))
        if not posts:
            raise ScrapeError(404)
        return await self.handle_post(scrape_item, posts[0], is_single_post=True)

    @error_handling_wrapper
    async def all_posts(self, scrape_item: ScrapeItem, date_range: DateRange | None = None) -> None:
        api_url = self.POSTS_URL
        if date_range:
            api_url = api_url.update_query(date_range.as_query())
        scrape_item.setup_as_profile(self.create_title("Posts"))
        await self.iter_posts(scrape_item, api_url)

    async def post_pager(self, url: AbsoluteHttpURL, init_page: int | None = None) -> AsyncIterable[Post]:
        had_at_least_1_post = False
        for page in itertools.count(init_page or 1):
            n_post = 0
            api_url = url.update_query(per_page=_POST_PER_REQUEST, page=page)
            posts = await self.__make_request(PostSequence, api_url)
            for post in posts:
                n_post += 1
                had_at_least_1_post = True
                yield post
            if n_post < _POST_PER_REQUEST:
                break
        if not had_at_least_1_post:
            raise ScrapeError(404)


class WordPressSoupCrawler(WordPressBaseCrawler, is_abc=True):
    @abstractmethod
    async def category_or_tag(
        self, scrape_item: ScrapeItem, colletion_type: ColletionType, date_range: DateRange | None = None
    ) -> None: ...

    @abstractmethod
    async def post(self, scrape_item: ScrapeItem) -> None: ...

    @abstractmethod
    async def all_posts(self, scrape_item: ScrapeItem, date_range: DateRange | None = None) -> None: ...

    @abstractmethod
    async def post_pager(self, api_url: AbsoluteHttpURL) -> None: ...


def _date_from_query_param(url: AbsoluteHttpURL, query_param: str) -> datetime.datetime | None:
    if value := url.query.get(query_param):
        return _parse_aware_datetime(value)


def _parse_aware_datetime(value: str) -> datetime.datetime | None:
    try:
        parsed_date = datetime.datetime.fromisoformat(value)
        if parsed_date.tzinfo is None:
            parsed_date.replace(tzinfo=datetime.UTC)
        return parsed_date
    except Exception:
        return


# TODO: Move to utils
def unique(iterable: Iterable[_T], *, hashable: bool = True) -> Iterable[_T]:
    """Yields unique values from iterable, keeping original order"""
    if hashable:
        seen: set[_T] | list[_T] = set()
        add: Callable[[_T], None] = seen.add
    else:
        seen = []
        add = seen.append

    for value in iterable:
        if value not in seen:
            add(value)
            yield value
