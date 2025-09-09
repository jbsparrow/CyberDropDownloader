from __future__ import annotations

import dataclasses
import itertools
from typing import TYPE_CHECKING, ClassVar
from xml.etree import ElementTree

from cyberdrop_dl.crawlers.xenforo.xenforo import XenforoCrawler
from cyberdrop_dl.exceptions import MaxChildrenError, ScrapeError

if TYPE_CHECKING:
    import datetime
    from collections.abc import Iterable

    from cyberdrop_dl.crawlers._forum import Thread
    from cyberdrop_dl.crawlers.crawler import SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem

N_POSTS_PER_PAGE = 15


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class Post:
    id: int
    title: str
    xml: ElementTree.Element[str]
    date: datetime.datetime | None = None

    @staticmethod
    def new(element: ElementTree.Element[str]) -> Post:
        title, id_ = element.attrib["title"], int(element.attrib["id"])
        return Post(id_, title, element)

    @property
    def images(self) -> Iterable[str]:
        return (image.attrib["main_url"] for image in self.xml.iter("image"))


# TODO: make a super class of Xenforo an inherit from that instead of Xenforo itself
class vBulletinCrawler(XenforoCrawler, is_abc=True):  # noqa: N801
    # TODO: Make this crawler more general, potentially scraping the actual html of a page like xenforo
    # Current limitations
    # 1. It can't get the content (text) of the actual post. (It's not included in the API response of most sites)
    # 2. Must vBulletin sites have the API disabled
    # 3. It has no date information
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Threads": (
            "/threads/<thread_name>",
            "/posts/<post_id>",
            "/goto/<post_id>",
        ),
    }
    VBULLETIN_LOGIN_COOKIE_NAME: ClassVar = ""
    VBULLETIN_THREAD_QUERY_PARAM: ClassVar = "t"
    VBULLETIN_POST_QUERY_PARAM: ClassVar = "p"
    VBULLETIN_API_ENDPOINT: ClassVar[AbsoluteHttpURL]

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        REQUIRED_FIELDS = ("VBULLETIN_LOGIN_COOKIE_NAME", "VBULLETIN_API_ENDPOINT")
        for field_name in REQUIRED_FIELDS:
            assert getattr(cls, field_name, None), f"Subclass {cls.__name__} must override: {field_name}"
        # TODO: Use the same name for these classvars across all crawlers
        cls.XF_USER_COOKIE_NAME = cls.VBULLETIN_LOGIN_COOKIE_NAME
        cls.XF_PAGE_URL_PART_NAME = "page"
        cls.XF_POST_URL_PART_NAME = "post"

    async def async_startup(self) -> None:
        if not self.logged_in:
            login_url = self.PRIMARY_URL / "login.php"
            await self._login(login_url)

        self.register_cache_filter(self.PRIMARY_URL, lambda _: True)

    async def check_login_with_request(self, *_) -> tuple[str, bool]:
        # TODO: Support login
        return "", False

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        # TODO: Handle more URLs
        if self.login_required and not self.logged_in:
            return
        await self.fetch_thread(scrape_item)

    async def process_thread(self, scrape_item: ScrapeItem, thread: Thread) -> None:
        title: str = ""
        if thread.post_id and self.scrape_single_forum_post:
            api_url = self.VBULLETIN_API_ENDPOINT.with_query({self.VBULLETIN_POST_QUERY_PARAM: str(thread.post_id)})
        else:
            api_url = self.VBULLETIN_API_ENDPOINT.with_query({self.VBULLETIN_THREAD_QUERY_PARAM: str(thread.id)})

        root_xml = await self.get_xml(api_url)
        if (thread_element := root_xml.find("thread")) is not None:
            title = self.create_title(thread_element.attrib["title"], thread_id=thread.id)
            scrape_item.setup_as_forum(title)
        else:
            raise ScrapeError(422)

        await self.process_posts(scrape_item, thread, root_xml)

    async def process_posts(self, scrape_item: ScrapeItem, thread: Thread, root_xml: ElementTree.Element[str]) -> None:
        if thread.page:
            posts = itertools.islice(root_xml.iter("post"), (thread.page - 1) * N_POSTS_PER_PAGE)
        else:
            posts = root_xml.iter("post")

        last_post_id = thread.post_id
        for element in posts:
            post = Post.new(element)
            if thread.post_id and thread.post_id > post.id:
                continue
            new_scrape_item = scrape_item.create_child(
                thread.url.update_query({self.VBULLETIN_POST_QUERY_PARAM: str(post.id)})
            )
            await self.post(new_scrape_item, post)
            last_post_id = post.id
            try:
                scrape_item.add_children()
            except MaxChildrenError:
                break

        if last_post_id:
            last_post_url = thread.url.update_query({self.VBULLETIN_POST_QUERY_PARAM: str(last_post_id)})
            await self.write_last_forum_post(thread.url, last_post_url)

    async def post(self, scrape_item: ScrapeItem, post: Post) -> None:
        title = self.create_separate_post_title(post.title, str(post.id), None)
        scrape_item.setup_as_post(title)
        for image in post.images:
            new_scrap_item = scrape_item.create_child(self.parse_url(image))
            self.handle_external_links(new_scrap_item)
            scrape_item.add_children()

    async def get_xml(self, url: AbsoluteHttpURL) -> ElementTree.Element[str]:
        root_xml = ElementTree.XML(await self.request_text(url))
        if error := root_xml.find("error"):
            details = error.attrib["details"]
            error_code = 403 if error.attrib["type"] == "permissions" and "unknown" not in details.casefold() else 422
            raise ScrapeError(error_code, message=details)
        return root_xml
