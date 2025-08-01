"""
- https://meta.discourse.org/t/available-settings-for-global-rate-limits-and-throttling/78612
- https://docs.discourse.org/
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from bs4 import BeautifulSoup
from pydantic import BaseModel

from cyberdrop_dl.crawlers._forum import MessageBoardCrawler
from cyberdrop_dl.exceptions import MaxChildrenError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper, unique

from .models import AvailablePost, PostStream, Topic

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Iterable

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem

_T = TypeVar("_T")
_MAX_POSTS_PER_REQUEST = 50
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class DiscourseCrawler(MessageBoardCrawler, is_generic=True):
    SUPPORTED_PATHS: ClassVar = {
        "Topic": (
            "/t/<topic_name>/<topic_id>",
            "/t/<topic_name>/<topic_id>/<post_number>",
        ),
        "Attachments": "/uploads/...",
        "**NOTE**": "If the URL includes <post_number>, posts with a number lower that it won't be scraped",
    }
    SUPPORTS_THREAD_RECURSION = False

    def __post_init__(self) -> None:
        self.scraped_topics_ids: set[int] = set()

    @staticmethod
    def is_attachment(link: AbsoluteHttpURL) -> bool:
        return "uploads" in link.parts

    async def handle_internal_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL | None = None) -> None:
        link = link or scrape_item.url
        if len(link.parts) < 5 and not link.suffix:
            return
        await super().handle_internal_link(scrape_item, link)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["uploads", _, *rest]:
                return await self.handle_internal_link(scrape_item)
            case ["t", _, topic_id, *rest]:
                post_number = int(rest[0]) if rest else None
                return await self.topic_from_id(scrape_item, int(topic_id), post_number)
            case _:
                raise ValueError

    async def make_request(self, model_cls: type[_ModelT], path: str, params: dict[str, Any] | None = None) -> _ModelT:
        api_url = self.PRIMARY_URL.joinpath(path)
        async with self.request_limiter:
            json_text = await self.client.get_text(self.DOMAIN, api_url, request_params={"params": params})
        return model_cls.model_validate_json(json_text, by_alias=True, by_name=True)

    @error_handling_wrapper
    async def topic_from_id(self, scrape_item: ScrapeItem, topic_id: int, post_number: int | None = None) -> None:
        if topic_id in self.scraped_topics_ids:
            return
        self.scraped_topics_ids.add(topic_id)
        topic = await self.make_request(Topic, f"t/{topic_id}.json")
        topic.init_post_number = post_number or 1
        await self.topic(scrape_item, topic)

    @error_handling_wrapper
    async def topic(self, scrape_item: ScrapeItem, topic: Topic) -> None:
        title = self.create_title(topic.title, thread_id=topic.id)
        scrape_item.setup_as_forum(title)
        scrape_item.possible_datetime = to_timestamp(topic.created_at)
        if topic.image_url:
            await self.handle_link(scrape_item, self.parse_url(topic.image_url))
        await self.process_posts(scrape_item, topic)

    async def forum(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    def parse_thread(self, *args, **kwargs) -> None:
        raise NotImplementedError

    async def thread(self, scrape_item: ScrapeItem, thread: Topic) -> None:
        await self.topic(scrape_item, thread)

    @error_handling_wrapper
    async def process_posts(self, scrape_item: ScrapeItem, topic: Topic) -> None:
        last_post_id = None
        async for post in self.iter_posts(topic):
            new_scrape_item = scrape_item.create_child(
                self.PRIMARY_URL / post.path.removeprefix("/"),
                possible_datetime=to_timestamp(post.created_at),
            )
            await self.post(new_scrape_item, post)
            last_post_id = post.id
            try:
                scrape_item.add_children()
            except MaxChildrenError:
                break

        if last_post_id:
            topic_url = self.PRIMARY_URL / topic.path.removeprefix("/")
            post_url = topic_url / str(last_post_id)
            await self.write_last_forum_post(topic_url, post_url)

    async def iter_posts(self, topic: Topic) -> AsyncIterable[AvailablePost]:
        for offset in itertools.count(topic.init_post_number - 1, _MAX_POSTS_PER_REQUEST):
            remaining = topic.stream[offset : offset + _MAX_POSTS_PER_REQUEST]
            if not remaining:
                return
            stream = await self.make_request(PostStream, f"t/{topic.id}/posts.json", {"post_ids[]": remaining})
            for post in stream.posts:
                yield post
                if topic.init_post_number != 1 and self.scrape_single_forum_post:
                    return

    async def post(self, scrape_item: ScrapeItem, post: AvailablePost) -> None:
        title = self.create_separate_post_title(post.title, str(post.id), post.created_at)
        scrape_item.setup_as_post(title)
        for link in self.extract_links(post):
            await self.handle_link(scrape_item, link)

    def extract_links(self, post: AvailablePost) -> Iterable[AbsoluteHttpURL]:
        def iter_links() -> Iterable[AbsoluteHttpURL]:
            soup = BeautifulSoup(post.content_html, "html.parser")
            images = css.iget(soup, *css.images)
            links = css.iget(soup, *css.links)
            external_links = (ref.url for ref in post.link_counts)
            for link_str in unique(itertools.chain(external_links, images, links)):
                try:
                    if link_str:
                        yield self.parse_url(link_str)
                except Exception:
                    continue

        return unique(iter_links())

    def parse_url(
        self, link_str: str, relative_to: AbsoluteHttpURL | None = None, *, trim: bool = True
    ) -> AbsoluteHttpURL:
        return _clean_url(super().parse_url(link_str, relative_to, trim=trim))


def _clean_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    # Skip domain to also download attachments from a different discourse site
    if "optimized" not in url.parts:
        return url
    original_name = f"{url.name.rsplit('_', 2)[0]}{url.suffix}"
    original_path = url.raw_path.replace("/optimized/", "/original/")
    return url.with_path(original_path, encoded=True, keep_fragment=True, keep_query=True).with_name(
        original_name, keep_fragment=True, keep_query=True
    )
