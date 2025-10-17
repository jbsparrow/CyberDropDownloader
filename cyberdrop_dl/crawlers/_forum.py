"""Base crawlers to scrape any message board / forum

If the message board has a public API, inherit from MessageBoard (ex: Discourse)

If the message board needs to scrape the actual HTML of page, Inherit for HTMLMessageBoard

"""
# ruff : noqa: RUF009

from __future__ import annotations

import asyncio
import base64
import dataclasses
import datetime
import re
from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar, Protocol, final

from bs4 import BeautifulSoup, Tag

from cyberdrop_dl.constants import HTTP_REGEX_LINKS
from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import LoginError, MaxChildrenError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dates import TimeStamp, to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between, is_blob_or_svg

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable, Sequence

    from aiohttp_client_cache.response import AnyResponse

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem

LINK_TRASH_MAPPING = {".th.": ".", ".md.": ".", "ifr": "watch"}

Selector = css.CssAttributeSelector


@dataclasses.dataclass(frozen=True, slots=True)
class PostSelectors:
    article: str  # the entire html of the post (comments, attachments, user avatar, signature, etc...)
    content: str  # text, links and images (NO attachments)
    id: Selector
    attachments: Selector
    article_trash: Sequence[str] = ("signature", "footer")
    content_trash: Sequence[str] = ("blockquote", "fauxBlockLink")

    # Most sites should only need to overwrite the attributes above
    date: Selector = Selector("time", "datetime")
    embeds: Selector = Selector("iframe", "src")
    images: Selector = Selector("img.bbImage", "src")
    a_tag_w_image: Selector = Selector("a:has(img.bbImage)[href]", "href")
    lazy_load_embeds: Selector = Selector('[class*=iframe][onclick*="loadMedia(this, \'//"]', "onclick")
    links: Selector = Selector("a:not(:has(img))", "href")
    videos: Selector = Selector("video source", "src")


@dataclasses.dataclass(frozen=True, slots=True)
class MessageBoardSelectors:
    posts: PostSelectors
    confirmation_button: Selector
    next_page: Selector
    last_page: Selector
    current_page: Selector
    title: Selector
    title_trash: Sequence[str] = ("span",)


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class ForumPost:
    id: int
    date: datetime.datetime | None
    article: Tag = dataclasses.field(compare=False)
    content: Tag = dataclasses.field(compare=False)

    @staticmethod
    def new(article: Tag, selectors: PostSelectors) -> ForumPost:
        for trash in selectors.article_trash:
            css.decompose(article, trash)
        content = css.select_one(article, selectors.content)
        for trash in selectors.content_trash:
            css.decompose(article, trash)
        try:
            date = datetime.datetime.fromisoformat(css.select_one_get_attr(article, *selectors.date))
        except Exception:
            date = None

        id_str = css.get_attr(article, selectors.id.attribute)
        post_id = int(id_str.rsplit("-", 1)[-1])
        return ForumPost(post_id, date, article, content)

    @property
    def timestamp(self) -> TimeStamp | None:
        if self.date:
            return to_timestamp(self.date)


class ForumPostProtocol(Protocol):
    # Concrete classes may define their own custom `ForumPost` class (ex: a Pydantic Model from an API response)
    # Those classes need to satisfy this Protocol to make sure they work with all of `MessageBoard` methods
    # This is just identify type errors.
    # Subclass implementation does not need to conform to this if they override the necessary methods
    @property
    def id(self) -> int: ...
    @property
    def date(self) -> datetime.datetime | None: ...
    @property
    def article(self) -> Tag: ...
    @property
    def content(self) -> Tag: ...
    @property
    def timestamp(self) -> TimeStamp | None: ...


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class Thread:
    id: int
    name: str
    page: int
    post_id: int | None
    url: AbsoluteHttpURL


class ThreadProtocol(Protocol):
    # Concrete classes may define their own custom `Thread` class (ex: discourse defines `Topic` from an API Response)
    # Those classes need to satisfy this Protocol to make sure they work with all of `MessageBoard` methods
    # This is just identify type errors.
    # Subclass implementation does not need to conform to this if they override the necessary methods
    @property
    def id(self) -> int: ...
    @property
    def name(self) -> str: ...
    @property
    def page(self) -> int: ...
    @property
    def post_id(self) -> int | None: ...
    @property
    def url(self) -> AbsoluteHttpURL: ...


class MessageBoardCrawler(Crawler, is_abc=True):
    """Base crawler for every MessageBoard.

    A Message board should have: forums, threads (also known as topics) and posts.

    Concrete classes MUST:
    - implement `parse_thread`
    - implement `make_post_url`
    - implement `thread`
    - implement `post`

    Concrete classes SHOULD define `ATTACHMENT_HOSTS` if internal images of the site are stored on servers with a different domain

    NOTE: Always use this crawler as base, even if the message board logic does not match perfectly.

    In those cases, override `fetch`,`fetch_thread`, `parse_url` or any other non final method as needed

    This crawler is NOT meant to scrape image boards (like 4chan)
    """

    THREAD_PART_NAMES: ClassVar[Sequence[str]] = "thread", "topic", "tema", "threads", "topics", "temas"
    ATTACHMENT_URL_PARTS: ClassVar[Sequence[str]] = "attachments", "data", "uploads"
    ATTACHMENT_HOSTS: ClassVar[Sequence[str]] = ()
    SUPPORTS_THREAD_RECURSION: ClassVar[bool] = False
    LOGIN_USER_COOKIE_NAME: ClassVar[str] = ""

    # True: Login is mandatory. If login fails, the crawler will be disabled
    # False: Login is optional, but CDL will try to log in anyway. ex: Forums where only some threads require auth
    # None: Completely skip login check and request. Always try to scrape as is the user is logged in
    # TODO: move login logic to the base crawler
    login_required: ClassVar[bool | None] = None

    @classmethod
    @abstractmethod
    def parse_thread(cls, url: AbsoluteHttpURL, thread_name_and_id: str) -> ThreadProtocol: ...

    @abstractmethod
    async def post(self, scrape_item: ScrapeItem, /, post: ForumPostProtocol) -> None: ...

    @abstractmethod
    async def thread(self, scrape_item: ScrapeItem, /, thread: ThreadProtocol) -> None: ...

    async def forum(self, scrape_item: ScrapeItem) -> None:
        # Subclasses can define custom logic for this method.
        # They would need to also override `fetch` since the default fetch does not take this method into account
        raise NotImplementedError

    async def resolve_confirmation_link(self, url: AbsoluteHttpURL, /) -> AbsoluteHttpURL | None:
        # Not every forum has confirmation link so overriding this method is optional
        # Implementation of this method MUST return `None` instead of raising an error
        raise NotImplementedError

    async def async_startup(self) -> None:
        await self.login()

    @final
    async def login(self) -> None:
        if self.login_required is None:
            return

        if not self.logged_in:
            login_url = self.PRIMARY_URL / "login"
            await self._login(login_url)

    @final
    @property
    def scrape_single_forum_post(self) -> bool:
        return self.manager.config_manager.settings_data.download_options.scrape_single_forum_post

    @final
    @property
    def max_thread_depth(self) -> int:
        return self.manager.config_manager.settings_data.download_options.maximum_thread_depth

    @final
    @property
    def max_thread_folder_depth(self):
        return self.manager.config.download_options.maximum_thread_folder_depth

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if not self.logged_in and self.login_required is True:
            return
        scrape_item.url = self.parse_url(str(scrape_item.url))
        if self.is_attachment(scrape_item.url):
            return await self.handle_internal_link(scrape_item)
        if is_confirmation_link(scrape_item.url):
            return await self.follow_confirmation_link(scrape_item)

        await self.fetch_thread(scrape_item)

    async def fetch_thread(self, scrape_item: ScrapeItem) -> None:
        thread_part_index = len(self.PRIMARY_URL.parts)
        # https://github.com/jbsparrow/CyberDropDownloader/issues/1165#issuecomment-3086739753
        if self.PRIMARY_URL.parts[-1] == "":
            thread_part_index -= 1
        match scrape_item.url.parts[thread_part_index:]:
            case [thread_part, thread_name_and_id, *_] if thread_part in self.THREAD_PART_NAMES:
                self.check_thread_recursion(scrape_item)
                thread = self.parse_thread(scrape_item.url, thread_name_and_id)
                return await self.thread(scrape_item, thread)
            case ["goto" | "posts", _, *_]:
                self.check_thread_recursion(scrape_item)
                return await self.follow_redirect(scrape_item)
            case _:
                raise ValueError

    def is_attachment(self, link: AbsoluteHttpURL | str) -> bool:
        if not link:
            return False
        if isinstance(link, str):
            link = self.parse_url(link)
        by_parts = len(link.parts) > 2 and any(p in link.parts for p in self.ATTACHMENT_URL_PARTS)
        by_host = any(host in link.host for host in self.ATTACHMENT_HOSTS)
        return by_parts or by_host

    @final
    async def follow_confirmation_link(self, scrape_item: ScrapeItem) -> None:
        url = await self.resolve_confirmation_link(scrape_item.url)
        if url:  # If there was an error, this will be None
            scrape_item.url = url
            # This could end up back in here if the URL goes to another thread
            return self.handle_external_links(scrape_item)

    @final
    def check_thread_recursion(self, scrape_item: ScrapeItem) -> None:
        if self.stop_thread_recursion(scrape_item):
            parents = f"{len(scrape_item.parent_threads)} parent thread(s)"
            msg = (
                f"Skipping nested thread URL with {parents}:"
                f"URL: {scrape_item.url}\n"
                f"Parent:  {scrape_item.parent}\n"
                f"Origin:  {scrape_item.origin}\n"
            )
            raise MaxChildrenError(msg)

        self.limit_nexted_thread_folders(scrape_item)

    @final
    def limit_nexted_thread_folders(self, scrape_item: ScrapeItem) -> None:
        if self.max_thread_folder_depth is None:
            return
        n_parents = len(scrape_item.parent_threads)
        if n_parents > self.max_thread_folder_depth:
            scrape_item.parent_title = scrape_item.parent_title.rsplit("/", 1)[0]
            if not self.separate_posts:
                return
            scrape_item.parent_title = scrape_item.parent_title.rsplit("/", 1)[0]

    @final
    def stop_thread_recursion(self, scrape_item: ScrapeItem) -> bool:
        if n_parents := len(scrape_item.parent_threads):
            if n_parents > self.max_thread_depth:
                return True

            return self.SUPPORTS_THREAD_RECURSION and bool(self.max_thread_depth)

        return False

    @final
    @error_handling_wrapper
    async def handle_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL) -> None:
        if link == self.PRIMARY_URL:
            return
        if self.is_attachment(link):
            return await self.handle_internal_link(scrape_item, link)
        if self.PRIMARY_URL.host == link.host:
            self.create_task(self.run(scrape_item.create_child(link)))
            return
        new_scrape_item = scrape_item.create_child(link)
        self.handle_external_links(new_scrape_item)
        scrape_item.add_children()

    @error_handling_wrapper
    async def handle_internal_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL | None = None) -> None:
        link = link or scrape_item.url
        filename, ext = self.get_filename_and_ext(link.name)
        new_scrape_item = scrape_item.copy()
        new_scrape_item.add_to_parent_title("Attachments")
        new_scrape_item.part_of_album = True
        await self.handle_file(link, new_scrape_item, filename, ext)

    @final
    async def write_last_forum_post(self, thread_url: AbsoluteHttpURL, last_post_url: AbsoluteHttpURL | None) -> None:
        if not last_post_url or last_post_url == thread_url:
            return
        self.manager.log_manager.write_last_post_log(last_post_url)

    # TODO: Move this to the base crawler
    # TODO: Define an unified workflow for crawlers to perform and check login
    @final
    @error_handling_wrapper
    async def _login(self, login_url: AbsoluteHttpURL) -> None:
        session_cookie = self.get_cookie_value(self.LOGIN_USER_COOKIE_NAME)
        msg = f"No cookies found for {self.FOLDER_DOMAIN}"
        if not session_cookie and self.login_required:
            raise LoginError(message=msg)

        _, self.logged_in = await self.check_login_with_request(login_url)
        if self.logged_in:
            return
        if session_cookie:
            msg = f"Cookies for {self.FOLDER_DOMAIN} are not valid."
        if self.login_required:
            raise LoginError(message=msg)

        msg += " Scraping without an account"
        self.log(msg, 30)

    async def check_login_with_request(self, login_url: AbsoluteHttpURL) -> tuple[str, bool]:
        text = await self.request_text(login_url, cache_disabled=True)
        logged_in = '<span class="p-navgroup-user-linkText">' in text or "You are already logged in." in text
        return text, logged_in


class HTMLMessageBoardCrawler(MessageBoardCrawler, is_abc=True):
    """Base crawler that knows how to scrape the html of every MessageBoard.

    Threads of the MessageBoard MUST be paginated.

    Concrete classes MUST:
    - define: `SELECTORS`, `POST_URL_PART_NAME` and `PAGE_URL_PART_NAME`

    This crawler delegates images to other crawlers by default
    Concrete classes MAY handle images themselves if they know how to. This will improve performance by reducing the number of requests

    To handle images, concrete classes need to:
    - override `IGNORE_EMBEDED_IMAGES_SRC` to `False`
    - override `is_thumbnail`
    - override `thumbnail_to_img`

    Concrete classes SHOULD define `ATTACHMENT_HOSTS` if internal images of the site are stored on servers with a different domain
    """

    IGNORE_EMBEDED_IMAGES_SRC = True
    SELECTORS: ClassVar[MessageBoardSelectors]
    POST_URL_PART_NAME: ClassVar[str]
    PAGE_URL_PART_NAME: ClassVar[str]

    def __init_subclass__(cls, is_abc: bool = False, **kwargs) -> None:
        super().__init_subclass__(is_abc=is_abc, **kwargs)
        if is_abc:
            return
        REQUIRED_FIELDS = "SELECTORS", "POST_URL_PART_NAME", "PAGE_URL_PART_NAME"
        for field_name in REQUIRED_FIELDS:
            assert getattr(cls, field_name, None), f"Subclass {cls.__name__} must override: {field_name}"

    def __post_init__(self) -> None:
        self.scraped_threads = set()

    @final
    async def async_startup(self) -> None:
        await super().async_startup()
        self.register_cache_filter(self.PRIMARY_URL, self.check_is_not_last_page)

    async def check_is_not_last_page(self, response: AnyResponse) -> bool:
        return await check_is_not_last_page(response, self.SELECTORS)

    @classmethod
    def is_thumbnail(cls, link: AbsoluteHttpURL) -> bool:
        return False

    @classmethod
    def thumbnail_to_img(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        return None

    @classmethod
    def parse_thread(cls, url: AbsoluteHttpURL, thread_name_and_id: str) -> ThreadProtocol:
        return parse_thread(url, thread_name_and_id, cls.PAGE_URL_PART_NAME, cls.POST_URL_PART_NAME)

    @classmethod
    def make_post_url(cls, thread: ThreadProtocol, post_id: int) -> AbsoluteHttpURL:
        return thread.url / f"{cls.POST_URL_PART_NAME}-{post_id}"

    @error_handling_wrapper
    async def thread(self, scrape_item: ScrapeItem, /, thread: ThreadProtocol) -> None:
        scrape_item.setup_as_forum("")
        if thread.url in self.scraped_threads:
            return

        scrape_item.parent_threads.add(thread.url)
        if self.scrape_single_forum_post and not thread.post_id:
            msg = "`--scrape-single-forum-post` is `True`, but the provided URL has no post id"
            raise ScrapeError("User Error", msg)

        self.scraped_threads.add(thread.url)
        await self.process_thread(scrape_item, thread)

    async def process_thread(self, scrape_item: ScrapeItem, thread: ThreadProtocol) -> None:
        title: str = ""
        last_post_url = thread.url
        async for soup in self.thread_pager(scrape_item):
            if not title:
                try:
                    title = self.create_title(get_post_title(soup, self.SELECTORS), thread_id=thread.id)
                except ScrapeError as e:
                    self.log_debug("Got an unprocessable soup", 40, exc_info=e)
                    raise
                scrape_item.add_to_parent_title(title)

            continue_scraping, last_post_url = self.process_thread_page(scrape_item, thread, soup)
            if not continue_scraping:
                break

        await self.write_last_forum_post(thread.url, last_post_url)

    def process_thread_page(
        self, scrape_item: ScrapeItem, thread: ThreadProtocol, soup: BeautifulSoup
    ) -> tuple[bool, AbsoluteHttpURL]:
        continue_scraping = False
        post_url = thread.url
        for article in soup.select(self.SELECTORS.posts.article):
            current_post = ForumPost.new(article, self.SELECTORS.posts)
            continue_scraping, scrape_this_post = check_post_id(
                thread.post_id, current_post.id, self.scrape_single_forum_post
            )
            if scrape_this_post:
                post_url = self.make_post_url(thread, current_post.id)
                new_scrape_item = scrape_item.create_new(
                    thread.url,
                    possible_datetime=current_post.timestamp,
                    add_parent=post_url,
                )
                self.create_task(self.post(new_scrape_item, current_post))
                try:
                    scrape_item.add_children()
                except MaxChildrenError:
                    break

            if not continue_scraping:
                break
        return continue_scraping, post_url

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, post: ForumPostProtocol) -> None:
        scrape_item.setup_as_post("")
        post_title = self.create_separate_post_title(None, str(post.id), post.date)
        scrape_item.add_to_parent_title(post_title)
        seen, duplicates, tasks = set(), set(), []
        stats: dict[str, int] = {}
        max_children_error: MaxChildrenError | None = None
        try:
            for scraper in (
                self._attachments,
                self._images,
                self._videos,
                self._external_links,
                self._embeds,
                self._lazy_load_embeds,
            ):
                for link in scraper(post):
                    duplicates.add(link) if link in seen else seen.add(link)
                    scraper_name = scraper.__name__.removeprefix("_")
                    stats[scraper_name] = stats.get(scraper_name, 0) + 1
                    tasks.append(self.process_child(scrape_item, link, embeds="embeds" in scraper_name))
                    scrape_item.add_children()
        except MaxChildrenError as e:
            max_children_error = e

        if seen:
            self.log(f"[{self.FOLDER_DOMAIN}] post #{post.id} {stats = }")
        if duplicates:
            msg = f"Found duplicate links in post {scrape_item.parent}. Selectors are too generic: {duplicates}"
            self.log(msg, bug=True)
        await asyncio.gather(*tasks)
        if max_children_error is not None:
            raise max_children_error

    def _external_links(self, post: ForumPostProtocol) -> Iterable[str]:
        selector = self.SELECTORS.posts.links
        links = css.iselect(post.content, selector.element)
        valid_links = (link for link in links if not self.is_username_or_attachment(link))
        return iter_links(valid_links, selector.attribute)

    def _images(self, post: ForumPostProtocol) -> Iterable[str]:
        if self.IGNORE_EMBEDED_IMAGES_SRC:
            selector = self.SELECTORS.posts.a_tag_w_image
        else:
            selector = self.SELECTORS.posts.images
        images = css.iselect(post.content, selector.element)
        return iter_links(images, selector.attribute)

    def _videos(self, post: ForumPostProtocol) -> Iterable[str]:
        selector = self.SELECTORS.posts.videos
        videos = css.iselect(post.content, selector.element)
        return iter_links(videos, selector.attribute)

    def _attachments(self, post: ForumPostProtocol) -> Iterable[str]:
        selector = self.SELECTORS.posts.attachments
        attachments = css.iselect(post.article, selector.element)
        return iter_links(attachments, selector.attribute)

    def _embeds(self, post: ForumPostProtocol) -> Iterable[str]:
        selector = self.SELECTORS.posts.embeds
        embeds = css.iselect(post.content, selector.element)
        return iter_links(embeds, selector.attribute)

    def _lazy_load_embeds(self, post: ForumPostProtocol) -> Iterable[str]:
        selector = self.SELECTORS.posts.lazy_load_embeds
        for lazy_media in css.iselect(post.content, selector.element):
            yield get_text_between(css.get_attr(lazy_media, selector.attribute), "loadMedia(this, '", "')")

    async def thread_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        async for soup in self._web_pager(scrape_item.url, self.get_next_page):
            yield soup

    def get_next_page(self, soup: BeautifulSoup) -> str | None:
        return css.select_one_get_attr_or_none(soup, *self.SELECTORS.next_page)

    @final
    @error_handling_wrapper
    async def process_child(self, scrape_item: ScrapeItem, link_str: str, *, embeds: bool = False) -> None:
        link_str_ = pre_process_child(link_str, embeds)
        if not link_str_:
            return
        link = await self.get_absolute_link(link_str_)
        if not link:
            return
        if self.is_thumbnail(link):
            link = self.thumbnail_to_img(link)
            if not link:
                return self.log(f"Skipping thumbnail: {link}")
        await self.handle_link(scrape_item, link)

    async def get_absolute_link(self, link: str | AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        if isinstance(link, str):
            absolute_link = self.parse_url(clean_link_str(link))
        else:
            absolute_link = link
        if is_confirmation_link(absolute_link):
            return await self.resolve_confirmation_link(absolute_link)
        return absolute_link

    @error_handling_wrapper
    async def resolve_confirmation_link(self, link: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        if url := link.query.get("url"):
            url = base64.b64decode(url).decode("utf-8")
            if url.startswith("https://"):
                return self.parse_url(url)

        soup = await self.request_soup(link)
        selector = self.SELECTORS.confirmation_button
        confirm_button = soup.select_one(selector.element)
        if not confirm_button:
            return

        link_str: str = css.get_attr(confirm_button, selector.attribute)
        link_str = link_str.split('" class="link link--internal', 1)[0]
        new_link = self.parse_url(link_str)
        return await self.get_absolute_link(new_link)

    async def handle_internal_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL | None = None) -> None:
        link = link or scrape_item.url
        slug = link.name or link.parent.name
        if slug.isdigit():
            return await self.follow_redirect(scrape_item.create_new(link))

        await super().handle_internal_link(scrape_item, link)

    def is_username_or_attachment(self, link_obj: Tag) -> bool:
        if link_obj.select_one(".username"):
            return True
        try:
            if link_str := css.get_attr(link_obj, self.SELECTORS.posts.links.element):
                return self.is_attachment(link_str)
        except Exception:
            pass
        return False


def iter_links(links: Iterable[Tag], attribute: str) -> Iterable[str]:
    for link_tag in links:
        try:
            yield css.get_attr(link_tag, attribute)
        except Exception:
            continue


def parse_thread(
    url: AbsoluteHttpURL, thread_name_and_id: str, page_part_name: str, post_part_name: str
) -> ThreadProtocol:
    name_index = url.parts.index(thread_name_and_id)
    name, id_ = parse_thread_name_and_id(thread_name_and_id)
    page, post_id = get_thread_page_and_post(url, name_index, page_part_name, post_part_name)
    canonical_url = get_thread_canonical_url(url, name_index)
    return Thread(id_, name, page, post_id, canonical_url)


def parse_thread_name_and_id(thread_name_and_id: str) -> tuple[str, int]:
    try:
        name, id_str = thread_name_and_id.rsplit(".", 1)
    except ValueError:
        id_str, name = thread_name_and_id.split("-", 1)
    return name, int(id_str)


def get_thread_canonical_url(url: AbsoluteHttpURL, thread_name_index: int) -> AbsoluteHttpURL:
    new_parts = url.parts[1 : thread_name_index + 1]
    new_path = "/".join(new_parts)
    return url.with_path(new_path)


def get_thread_page_and_post(
    url: AbsoluteHttpURL, thread_name_index: int, page_name: str, post_name: str
) -> tuple[int, int | None]:
    extra_parts = url.parts[thread_name_index + 1 :]
    if url.fragment:
        extra_parts = *extra_parts, url.fragment

    def find_number(search_value: str) -> int | None:
        for sec in extra_parts:
            if search_value in sec:
                return int(sec.rsplit(search_value, 1)[-1].replace("-", "").strip())

    post_id = find_number(post_name)
    page_number = find_number(page_name) or 1
    return page_number, post_id


async def check_is_not_last_page(response: AnyResponse, selectors: MessageBoardSelectors) -> bool:
    soup = BeautifulSoup(await response.text(), "html.parser")
    return not is_last_page(soup, selectors)


def is_last_page(soup: BeautifulSoup, selectors: MessageBoardSelectors) -> bool:
    try:
        last_page = css.select_one_get_attr(soup, *selectors.last_page)
        current_page = css.select_one_get_attr(soup, *selectors.current_page)
    except (AttributeError, IndexError, css.SelectorError):
        return True
    return current_page == last_page


def get_post_title(soup: BeautifulSoup, selectors: MessageBoardSelectors) -> str:
    try:
        title_block = css.select_one(soup, selectors.title.element)
        for trash in selectors.title_trash:
            css.decompose(title_block, trash)
    except (AttributeError, AssertionError, css.SelectorError) as e:
        raise ScrapeError(429, message="Invalid response from forum. You may have been rate limited") from e

    if title := " ".join(css.get_text(title_block).split()):
        return title
    raise ScrapeError(422)


def extract_embed_url(embed_str: str) -> str:
    embed_str = embed_str.replace(r"\/\/", "https://www.").replace("\\", "")
    if match := re.search(HTTP_REGEX_LINKS, embed_str):
        return match.group(0).replace("www.", "")
    return embed_str


def clean_link_str(link: str) -> str:
    for old, new in LINK_TRASH_MAPPING.items():
        link = link.replace(old, new)
    return link


def is_confirmation_link(link: AbsoluteHttpURL) -> bool:
    return "masked" in link.parts or "link-confirmation" in link.path


def check_post_id(init_post_id: int | None, current_post_id: int, scrape_single_forum_post: bool) -> tuple[bool, bool]:
    """Checks if the program should scrape the current post.

    Returns (continue_scraping, scrape_this_post)"""
    if init_post_id:
        if init_post_id > current_post_id:
            return (True, False)
        elif init_post_id == current_post_id:
            return (not scrape_single_forum_post, True)
        else:
            return (not scrape_single_forum_post, not scrape_single_forum_post)

    assert not scrape_single_forum_post  # We should have raised an exception earlier
    return True, True


def pre_process_child(link_str: str, embeds: bool = False) -> str | None:
    assert isinstance(link_str, str)
    if embeds:
        link_str = extract_embed_url(link_str)

    if link_str and not is_blob_or_svg(link_str):
        return link_str
