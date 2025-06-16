"""
- https://meta.discourse.org/t/available-settings-for-global-rate-limits-and-throttling/78612
- https://docs.discourse.org/
"""

from __future__ import annotations

import itertools
import re
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from bs4 import BeautifulSoup
from pydantic import BaseModel

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import MaxChildrenError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from .models import AvailablePost, PostStream, Topic

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Callable, Iterable

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem

__all__ = ["DiscourseCrawler"]
_T = TypeVar("_T")
_MAX_POSTS_PER_REQUEST = 50
_ModelT = TypeVar("_ModelT", bound=BaseModel)
_HTTP_URL_REGEX = re.compile(
    r"https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,12}\b([-a-zA-Z0-9@:%_+.~#?&/=]*)"
)  # Same as Xenforo


# TODO: topic as simple html: /t/<id>?_escaped_fragment_
# TODO: topic as markdown: /raw/t/<id>


class MessageBoardCrawler(Crawler, is_abc=True):
    # TODO: make it a bit more general and make Xenforo and Reddit inherit from this

    @property
    def max_thread_depth(self) -> int:
        return self.manager.config_manager.settings_data.download_options.maximum_thread_depth

    @classmethod
    @abstractmethod
    def is_attachment(cls, url: AbsoluteHttpURL) -> bool: ...

    @error_handling_wrapper
    async def handle_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL) -> None:
        if link == self.PRIMARY_URL:
            return
        if self.is_attachment(link):
            await self.handle_internal_link(scrape_item.create_new(link))
        elif self.PRIMARY_URL.host in scrape_item.url.host and self.stop_thread_recursion(scrape_item):
            origin = scrape_item.origin()
            return self.log(f"Skipping nested thread URL {scrape_item.url} found on {origin}", 10)
        new_scrape_item = scrape_item.copy()
        new_scrape_item.type = None
        new_scrape_item.reset_childen()
        self.handle_external_links(new_scrape_item)
        scrape_item.add_children()

    async def handle_internal_link(self, scrape_item: ScrapeItem) -> None:
        if len(scrape_item.url.parts) < 5 and not scrape_item.url.suffix:
            return
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        scrape_item.add_to_parent_title("Attachments")
        scrape_item.part_of_album = True
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    def stop_thread_recursion(self, scrape_item: ScrapeItem) -> bool:
        if not self.max_thread_depth or (len(scrape_item.parent_threads) > self.max_thread_depth):
            return True
        return False

    async def write_last_forum_post(self, thread: Topic, last_post_id: int | None) -> None:
        if not last_post_id or last_post_id == thread.id:
            return
        last_post_url = self.parse_url(thread.path) / str(last_post_id)
        await self.manager.log_manager.write_last_post_log(last_post_url)


class DiscourseCrawler(MessageBoardCrawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar = {"Topic": "/t/<topic_name>/<topic_id>", "Attachments": ""}
    ATTACHMENT_PART: ClassVar[str] = "uploads"

    def __init_subclass__(cls, **kwargs) -> None:
        cls.SUPPORTED_PATHS = cls.SUPPORTED_PATHS | {"Attachments": f"/{cls.ATTACHMENT_PART}/..."}  # type: ignore
        super().__init_subclass__(**kwargs)

    def __post_init__(self) -> None:
        self.scraped_topics: set[int] = set()

    @classmethod
    def is_attachment(cls, link: AbsoluteHttpURL) -> bool:
        return cls.PRIMARY_URL.host in link.host and cls.ATTACHMENT_PART in link.parts

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if self.is_attachment(scrape_item.url):
            return await self.handle_internal_link(scrape_item)

        match scrape_item.url.parts[1:]:
            case ["t", topic_id]:
                return await self.topic_from_id(scrape_item, topic_id)
            case ["t", topic_id, post_id]:
                return await self.topic_from_id(scrape_item, topic_id, post_id)
            case ["c", category_id]:
                return await self.topic_from_id(scrape_item, category_id)
            case ["c", category_id, topic_id]:
                return await self.topic_from_id(scrape_item, category_id)
            case _:
                raise ValueError

    async def make_request(self, model_cls: type[_ModelT], path: str, params: dict[str, Any] | None = None) -> _ModelT:
        api_url = self.PRIMARY_URL.joinpath(path)
        async with self.request_limiter:
            json_text = await self.client.get_text(self.DOMAIN, api_url, request_params={"params": params})
        return model_cls.model_validate_json(json_text, by_alias=True, by_name=True)

    @error_handling_wrapper
    async def topic_from_id(
        self, scrape_item: ScrapeItem, topic_id: str | int, post_id: str | int | None = None
    ) -> None:
        init_post_number = int(post_id) if post_id else None
        if init_post_number and self.manager.config_manager.settings_data.download_options.scrape_single_forum_post:
            pass  # TODO: scrape single post

        topic = await self.make_request(Topic, f"t/{topic_id}.json")
        topic.init_post_number = init_post_number or 1
        await self.topic(scrape_item, topic)

    @error_handling_wrapper
    async def topic(self, scrape_item: ScrapeItem, topic: Topic) -> None:
        title = self.create_title(topic.title, thread_id=topic.id)
        scrape_item.setup_as_forum(title)
        scrape_item.possible_datetime = to_timestamp(topic.created_at)
        if topic.image_url:
            await self.handle_link(scrape_item, self.parse_url(topic.image_url))
        await self.process_posts(scrape_item, topic)

    @error_handling_wrapper
    async def process_posts(self, scrape_item: ScrapeItem, topic: Topic) -> None:
        last_post_id = None
        async for post in self.iter_posts(topic):
            new_scrape_item = scrape_item.create_child(
                self.parse_url(post.path), possible_datetime=to_timestamp(post.created_at)
            )
            await self.post(new_scrape_item, post)
            last_post_id = post.id
            try:
                scrape_item.add_children()
            except MaxChildrenError:
                break  # TODO: Use context manager to write last post ans rerais ethe exception

        await self.write_last_forum_post(topic, last_post_id)

    async def iter_posts(self, topic: Topic) -> AsyncIterable[AvailablePost]:
        for offset in itertools.count(topic.init_post_number - 1, _MAX_POSTS_PER_REQUEST):
            remaining = topic.stream[offset : offset + _MAX_POSTS_PER_REQUEST]
            if not remaining:
                return
            stream = await self.make_request(PostStream, f"/t/{topic.id}/posts.json", {"post_ids[]": remaining})
            for post in stream.posts:
                yield post

    async def post(self, scrape_item: ScrapeItem, post: AvailablePost) -> None:
        scrape_item.setup_as_post("")
        post_title = self.create_separate_post_title(post.title, str(post.id), None)
        scrape_item.add_to_parent_title(post_title)

        for link in self.extract_links(post):
            await self.handle_link(scrape_item, link)

    def extract_links(self, post: AvailablePost) -> Iterable[AbsoluteHttpURL]:
        def iter_links() -> Iterable[AbsoluteHttpURL]:
            external_links = (ref.url for ref in post.link_counts)
            for link_str in unique(itertools.chain(external_links, get_links_by_regex(post.content_html))):
                try:
                    yield self.parse_url(link_str)
                except Exception:
                    continue

        return unique(iter_links())

    def parse_url(self, link: str) -> AbsoluteHttpURL:
        return _clean_url(super().parse_url(link))


def _clean_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    # Skip domain to also download attachments from a different discourse site
    if "optimized" not in url.parts:
        return url
    original_name = f"{url.name.rsplit('_', 2)[0]}{url.suffix}"
    original_path = url.raw_path.replace("/optimized/", "/original/")
    return url.with_path(original_path, encoded=True, keep_fragment=True, keep_query=True).with_name(
        original_name, keep_fragment=True, keep_query=True
    )


# Overkill for this crawler since all the internal URLs have a known pattern
# But may be useful for others crawler that have html that is actually from another site
# TODO: Move to utils
def get_links_by_soup(html_content: str) -> Iterable[str]:
    soup = BeautifulSoup(html_content, "html.parser")
    for attr in ("href", "src", "data-src", "data-url"):
        for link_str in (css.get_attr(inner_tag, attr) for inner_tag in css.iselect(soup, f"[{attr}]")):
            if any(link_str.startswith(blob) for blob in ("javascript:", "data:")):
                continue
            if "/" not in link_str:
                link_str = f"/{link_str}"
            yield link_str


def get_links_by_regex(text: str) -> Iterable[str]:
    return (match.group() for match in re.finditer(_HTTP_URL_REGEX, text))


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


def _make_url_part_parser(
    part: str, index: int, coerce_to: Callable[[str], _T] = int
) -> Callable[[AbsoluteHttpURL], _T | None]:
    def get_id(url: AbsoluteHttpURL) -> _T | None:
        if part in url.parts:
            try:
                return coerce_to(url.parts[index].removesuffix(".json"))
            except (ValueError, IndexError, TypeError):
                return

    return get_id
