# ruff : noqa: RUF009

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from xml.etree import ElementTree

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import LoginError, MaxChildrenError, ScrapeError
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, parse_url

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyberdrop_dl.crawlers.crawler import SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


@dataclass(slots=True)
class Post:
    title: str
    id: int
    images: Iterable[ElementTree.Element[str]]

    @staticmethod
    def new(element: ElementTree.Element[str]) -> Post:
        title, id = element.attrib["title"], int(element.attrib["id"])
        images = (parse_url(image.attrib["main_url"]) for image in element.iter("image"))
        return Post(title, id, images)


@dataclass(frozen=True, slots=True)
class Thread:
    name: str
    id: int
    page: int | None
    post: int | None
    url: AbsoluteHttpURL
    full_url: AbsoluteHttpURL


class vBulletinCrawler(Crawler, is_abc=True):  # noqa: N801
    # TODO: Make this crawler more general, potentially scraping the actual html of a page
    # Current limitations
    # 1. It can not get the content (text) of the actual post. (It's not included in the API response)
    # 2. It only gets images
    # 3. It has no date information
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Threads": ("/threads/<thread_name>", "/posts/<post_id>", "/goto/<post_id>"),
    }
    LOGIN_REQUIRED: ClassVar = True
    THREAD_PART_NAME: ClassVar = "threads"
    LOGIN_COOKIE: ClassVar = ""
    N_POSTS_PER_PAGE: ClassVar = 15

    THREAD_QUERY_PARAM: ClassVar = "t"
    POST_QUERY_PARAM: ClassVar = "p"
    API_ENDPOINT: ClassVar[AbsoluteHttpURL] = None  # type: ignore

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        REQUIRED_FIELDS = ("API_ENDPOINT", "LOGIN_COOKIE")
        for field_name in REQUIRED_FIELDS:
            assert getattr(cls, field_name, None), f"Subclass {cls.__name__} must override: {field_name}"

    def __post_init__(self) -> None:
        self.scraped_threads = set()

    async def async_startup(self) -> None:
        if not self.logged_in:
            login_url = self.PRIMARY_URL / "login.php"
            await self.check_login(login_url)

        self.register_cache_filter(self.PRIMARY_URL, lambda _: True)

    @error_handling_wrapper
    async def check_login(self, *_) -> None:
        host_cookies = self.client.client_manager.cookies.filter_cookies(self.PRIMARY_URL)
        session_cookie = host_cookies.get(self.LOGIN_COOKIE)
        session_cookie = session_cookie.value if session_cookie else None
        msg = f"No cookies found for {self.FOLDER_DOMAIN}"
        self.logged_in = bool(session_cookie)
        if self.logged_in:
            return
        if self.LOGIN_REQUIRED:
            raise LoginError(message=msg)

        msg += " Scraping without an account"
        log(msg, 30)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if not self.logged_in and self.LOGIN_REQUIRED:
            return
        if self.THREAD_PART_NAME in scrape_item.url.parts:
            return await self.thread(scrape_item)
        raise ValueError

    def get_thread_info(self, url: AbsoluteHttpURL) -> Thread:
        if url.fragment.startswith("post"):
            post_number = _digits(url.fragment)
        else:
            post_number = _digits_or_none(url.query.get(self.POST_QUERY_PARAM))

        name_index = url.parts.index(self.THREAD_PART_NAME) + 1
        id_, name = url.parts[name_index].split("-", 1)
        thread_url = get_thread_canonical_url(url, name_index)
        page_number = _digits_or_none(next((p for p in url.parts if p.startswith("page")), None))
        query = {self.POST_QUERY_PARAM: str(post_number)} if post_number else None
        return Thread(name, int(id_), page_number, post_number, thread_url, url.with_query(query))

    @error_handling_wrapper
    async def thread(self, scrape_item: ScrapeItem) -> None:
        thread = self.get_thread_info(scrape_item.url)
        if thread.url in self.scraped_threads:
            return

        scrape_item.url = thread.full_url
        scrape_item.parent_threads.add(thread.url)
        self.scraped_threads.add(thread.url)
        if thread.post and self.manager.config_manager.settings_data.download_options.scrape_single_forum_post:
            api_url = self.API_ENDPOINT.with_query({self.POST_QUERY_PARAM: str(thread.post)})
        else:
            api_url = self.API_ENDPOINT.with_query({self.THREAD_QUERY_PARAM: str(thread.id)})

        root_xml = await self.get_xml(api_url)
        if thread_element := root_xml.find("thread"):
            title = self.create_title(thread_element.attrib["title"], thread_id=thread.id)
            scrape_item.setup_as_forum(title)
        else:
            raise ScrapeError(422)

        await self.process_posts(scrape_item, thread, root_xml)

    async def process_posts(
        self, scrape_item: ScrapeItem, thread: Thread, root_xml: ElementTree.ElementTree[str]
    ) -> None:
        posts = root_xml.iter("post")
        if thread.page:
            posts = itertools.islice(posts, (thread.page - 1) * self.N_POSTS_PER_PAGE)

        last_post_id = thread.post
        for element in posts:
            post = Post.new(element)
            if thread.post and thread.post > post.id:
                continue
            new_scrape_item = scrape_item.create_child(thread.url.update_query({self.POST_QUERY_PARAM: str(post.id)}))
            await self.post(new_scrape_item, post)
            last_post_id = post.id
            try:
                scrape_item.add_children()
            except MaxChildrenError:
                break

        await self.write_last_forum_post(thread.url, last_post_id)

    async def write_last_forum_post(self, thread: Thread, last_post_id: int | None) -> None:
        if not last_post_id or last_post_id == thread.post:
            return
        last_post_url = thread.url.update_query({self.POST_QUERY_PARAM: str(last_post_id)})
        await self.manager.log_manager.write_last_post_log(last_post_url)

    async def post(self, scrape_item: ScrapeItem, post: Post) -> None:
        scrape_item.setup_as_post("")
        post_title = self.create_separate_post_title(post.title, str(post.id), None)
        scrape_item.add_to_parent_title(post_title)
        for image_url in post.images:
            new_scrap_item = scrape_item.create_child(image_url)
            self.handle_external_links(new_scrap_item)
            scrape_item.add_children()

    async def get_xml(self, url: AbsoluteHttpURL) -> ElementTree.Element[str]:
        async with self.request_limiter:
            text = await self.client.get_text(self.DOMAIN, url)
        root_xml = ElementTree.XML(text)
        if error := root_xml.find("error"):
            details = error.attrib["details"]
            error_code = 403 if error.attrib["type"] == "permissions" and "unknown" not in details.casefold() else 422
            raise ScrapeError(error_code, msg=details)


def get_thread_canonical_url(url: AbsoluteHttpURL, thread_name_index: int) -> AbsoluteHttpURL:
    thread_parts = url.parts[1 : thread_name_index + 1]
    return url.with_path("/".join(thread_parts))


def _digits(string: str) -> int:
    return int(re.sub(r"\D", "", string).strip())


def _digits_or_none(string: str | None) -> int | None:
    if string and (value := _digits(string)) is not None:
        return value
