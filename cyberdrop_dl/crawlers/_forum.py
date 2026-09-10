"""Base crawlers to scrape any message board / forum

If the message board has a public API, inherit from MessageBoard (ex: Discourse)

If the message board needs to scrape the actual HTML of page, Inherit for HTMLMessageBoard

"""
# ruff : noqa: RUF009

from __future__ import annotations

import base64
import dataclasses
import datetime
import re
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, final

from bs4 import BeautifulSoup, Tag

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import LoginError, MaxChildrenError, ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import b64_pad, css, extr_text, is_blob_or_svg
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence

    from aiohttp import ClientResponse

    from cyberdrop_dl.url_objects import ScrapeItem

LINK_TRASH_MAPPING = {".th.": ".", ".md.": ".", "ifr": "watch"}
HTTP_REGEX_LINKS = re.compile(
    r"https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,12}\b([-a-zA-Z0-9@:%_+.~#?&/=]*)"
)


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
        content = css.select(article, selectors.content)
        for trash in selectors.content_trash:
            css.decompose(article, trash)
        try:
            date = datetime.datetime.fromisoformat(css.select(article, *selectors.date))
        except Exception:  # noqa: BLE001
            date = None

        id_str = css.attr(article, selectors.id.attribute)
        post_id = int(id_str.rsplit("-", 1)[-1])
        return ForumPost(post_id, date, article, content)

    @property
    def timestamp(self) -> float | None:
        if self.date:
            return self.date.timestamp()


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
    def timestamp(self) -> float | None: ...


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
    ATTACHMENT_URL_PARTS: ClassVar[tuple[str, ...]] = "attachments", "data", "uploads"
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

    async def resolve_confirmation_link(self, url: AbsoluteHttpURL, /) -> AbsoluteHttpURL | None:
        # Not every forum has confirmation link so overriding this method is optional
        # Implementation of this method MUST return `None` instead of raising an error
        raise NotImplementedError

    async def __async_post_init__(self) -> None:
        if self.login_required is None:
            return

        if not self._logged_in:
            login_url = self.PRIMARY_URL / "login"
            await self.login(login_url)

    @final
    @property
    def max_thread_depth(self) -> int:
        return self.config.max_thread_depth

    @final
    @property
    def max_thread_folder_depth(self) -> int | None:
        return self.config.max_thread_folder_depth

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if not self._logged_in and self.login_required is True:
            return None
        scrape_item.url = self.parse_url(str(scrape_item.url))
        if self.is_attachment(scrape_item.url):
            return await self.handle_internal_link(scrape_item)
        if is_confirmation_link(scrape_item.url):
            return await self._follow_confirmation_link(scrape_item)

        await self._fetch_thread(scrape_item)

    async def _fetch_thread(self, scrape_item: ScrapeItem) -> None:
        thread_part_index = len(self.PRIMARY_URL.parts)
        # https://github.com/Cyberdrop-DL/cyberdrop-dl/issues/1165#issuecomment-3086739753
        if self.PRIMARY_URL.parts[-1] == "":
            thread_part_index -= 1
        match scrape_item.url.parts[thread_part_index:]:
            case [thread_part, thread_name_and_id, *_] if thread_part in self.THREAD_PART_NAMES:
                self._check_thread_recursion(scrape_item)
                thread = self.parse_thread(scrape_item.url, thread_name_and_id)
                return await self.thread(scrape_item, thread)
            case ["goto" | "posts", _, *_]:
                self._check_thread_recursion(scrape_item)
                return await self.follow_redirect(scrape_item)
            case ["members", *_]:
                return None
            case [slug] if slug.startswith("#"):
                return None
            case _:
                raise ValueError

    @classmethod
    def is_attachment(cls, link: AbsoluteHttpURL | str) -> bool:
        if not link:
            return False
        if isinstance(link, str):
            link = cls.parse_url(link)
        by_parts = len(link.parts) > 2 and any(p in link.parts for p in cls.ATTACHMENT_URL_PARTS)
        by_host = any(host in link.host for host in cls.ATTACHMENT_HOSTS)
        return by_parts or by_host

    @final
    async def _follow_confirmation_link(self, scrape_item: ScrapeItem) -> None:
        url = await self.resolve_confirmation_link(scrape_item.url)
        if url:  # If there was an error, this will be None
            scrape_item.url = url
            # This could end up back in here if the URL goes to another thread
            return self.handle_external_links(scrape_item)

    @final
    def _check_thread_recursion(self, scrape_item: ScrapeItem) -> None:
        if self.stop_thread_recursion(scrape_item):
            threads = f"{len(scrape_item.parent_threads)} parent thread(s)"
            origin, parent = (scrape_item.parents[0], scrape_item.parents[-1]) if scrape_item.parents else (None, None)
            msg = (
                f"Skipping nested thread URL with {threads}:"
                f"URL: {scrape_item.url}\n"
                f"Parent:  {parent}\n"
                f"Origin:  {origin}\n"
            )
            raise MaxChildrenError(msg)

        self._limit_nexted_thread_folders(scrape_item)

    @final
    def _limit_nexted_thread_folders(self, scrape_item: ScrapeItem) -> None:
        if self.max_thread_folder_depth is None:
            return
        n_parents = len(scrape_item.parent_threads)
        if n_parents > self.max_thread_folder_depth:
            scrape_item.folders.pop()
            if not self.separate_posts:
                return
            scrape_item.folders.pop()

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
            return None
        if self.is_attachment(link):
            return await self.handle_internal_link(scrape_item, link)
        if self.PRIMARY_URL.host == link.host:
            self.create_task(self.run(scrape_item.create_child(link)))
            return None
        new_scrape_item = scrape_item.create_child(link)
        self.handle_external_links(new_scrape_item)
        scrape_item.add_children()

    @error_handling_wrapper
    async def handle_internal_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL | None = None) -> None:
        link = link or scrape_item.url
        filename, ext = self.get_filename_and_ext(link.name)
        new_scrape_item = scrape_item.copy()
        new_scrape_item.append_folders("Attachments")
        new_scrape_item.part_of_album = True
        await self.handle_file(link, new_scrape_item, filename, ext)

    # TODO: Move this to the base crawler
    # TODO: Define an unified workflow for crawlers to perform and check login
    @final
    @error_handling_wrapper
    async def login(self, login_url: AbsoluteHttpURL) -> None:
        session_cookie = self.cookies.get(self.LOGIN_USER_COOKIE_NAME)
        msg = f"No cookies found for {self.FOLDER_DOMAIN}"
        if not session_cookie and self.login_required:
            raise LoginError(message=msg)

        _, self._logged_in = await self.check_login_with_request(login_url)
        if self._logged_in:
            return
        if session_cookie:
            msg = f"Cookies for {self.FOLDER_DOMAIN} are not valid."
        if self.login_required:
            raise LoginError(message=msg)

        msg += " Scraping without an account"
        self.log.warning(msg)

    async def check_login_with_request(self, login_url: AbsoluteHttpURL) -> tuple[str, bool]:
        text = await self.request_text(login_url)
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

    IGNORE_EMBEDED_IMAGES_SRC: ClassVar[bool] = True
    SELECTORS: ClassVar[MessageBoardSelectors]
    POST_URL_PART_NAME: ClassVar[str]
    PAGE_URL_PART_NAME: ClassVar[str]

    def __init_subclass__(cls, *, is_abc: bool = False, **kwargs: Any) -> None:
        super().__init_subclass__(is_abc=is_abc, **kwargs)
        if is_abc:
            return
        REQUIRED_FIELDS = "SELECTORS", "POST_URL_PART_NAME", "PAGE_URL_PART_NAME"
        for field_name in REQUIRED_FIELDS:
            assert getattr(cls, field_name, None), f"Subclass {cls.__name__} must override: {field_name}"

    def __post_init__(self) -> None:
        self.scraped_threads: set[AbsoluteHttpURL] = set()

    @classmethod
    def is_thumbnail(cls, link: AbsoluteHttpURL) -> bool:
        assert link
        return False

    @classmethod
    def thumbnail_to_img(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        assert url
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
        self.scraped_threads.add(thread.url)
        await self._thread(scrape_item, thread)

    async def _thread(self, scrape_item: ScrapeItem, thread: ThreadProtocol) -> None:
        first_page, pages = await aio.peek_first(self.web_pager(scrape_item.url, self.get_next_page))
        try:
            title = get_post_title(first_page, self.SELECTORS)
        except ScrapeError as e:
            self.log.debug("Got an unprocessable soup", exc_info=e)
            raise
        else:
            scrape_item.append_folders(self.create_title(title, thread_id=thread.id))

        post_url = None
        try:
            async for soup in pages:
                for post in self._iter_posts(thread, soup):
                    post_url = self.make_post_url(thread, post.id)
                    new_scrape_item = scrape_item.create_new(thread.url, add_parent=post_url)
                    new_scrape_item.uploaded_at = post.timestamp
                    self.create_task(self.post(new_scrape_item, post))
                    scrape_item.add_children()
        finally:
            if post_url and post_url != thread.url:
                self.manager.scrape_mapper.logs.write_last_forum_post(post_url)

    def _iter_posts(self, thread: ThreadProtocol, soup: BeautifulSoup) -> Generator[ForumPost]:
        for article in soup.select(self.SELECTORS.posts.article):
            post = ForumPost.new(article, self.SELECTORS.posts)
            if thread.post_id and post.id < thread.post_id:
                continue

            yield post

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, post: ForumPostProtocol) -> None:
        scrape_item.setup_as_post("")
        post_title = self.create_separate_post_title(None, str(post.id), post.date)
        scrape_item.append_folders(post_title)
        stats: dict[str, int] = {}

        async with self.new_task_group() as tg:
            for scraper in (
                self._attachments,
                self._images,
                self._videos,
                self._external_links,
                self._embeds,
                self._lazy_load_embeds,
            ):
                for url in scraper(post):
                    scraper_name = scraper.__name__.removeprefix("_")
                    stats[scraper_name] = stats.get(scraper_name, 0) + 1
                    tg.create_task(self.process_child(scrape_item, url, embeds="embeds" in scraper_name))
                    scrape_item.add_children()

        if stats:
            self.log.info(f"post #{post.id} {stats = }")

    @classmethod
    def _external_links(cls, post: ForumPostProtocol) -> Iterable[str]:
        selector = cls.SELECTORS.posts.links
        links = css.iselect(post.content, selector.element)
        valid_links = (link for link in links if not cls.is_username_or_attachment(link))
        return iter_links(valid_links, selector.attribute)

    @classmethod
    def _images(cls, post: ForumPostProtocol) -> Iterable[str]:
        selector = cls.SELECTORS.posts.a_tag_w_image if cls.IGNORE_EMBEDED_IMAGES_SRC else cls.SELECTORS.posts.images
        images = css.iselect(post.content, selector.element)
        return iter_links(images, selector.attribute)

    @classmethod
    def _videos(cls, post: ForumPostProtocol) -> Iterable[str]:
        selector = cls.SELECTORS.posts.videos
        videos = css.iselect(post.content, selector.element)
        return iter_links(videos, selector.attribute)

    @classmethod
    def _attachments(cls, post: ForumPostProtocol) -> Iterable[str]:
        selector = cls.SELECTORS.posts.attachments
        attachments = css.iselect(post.article, selector.element)
        return iter_links(attachments, selector.attribute)

    @classmethod
    def _embeds(cls, post: ForumPostProtocol) -> Iterable[str]:
        selector = cls.SELECTORS.posts.embeds
        embeds = css.iselect(post.content, selector.element)
        return iter_links(embeds, selector.attribute)

    @classmethod
    def _lazy_load_embeds(cls, post: ForumPostProtocol) -> Iterable[str]:
        selector = cls.SELECTORS.posts.lazy_load_embeds
        for lazy_media in css.iselect(post.content, selector.element):
            yield extr_text(css.attr(lazy_media, selector.attribute), "loadMedia(this, '", "')")

    def get_next_page(self, soup: BeautifulSoup) -> str | None:
        try:
            return css.select(soup, *self.SELECTORS.next_page)
        except css.SelectorError:
            return None

    @final
    @error_handling_wrapper
    async def process_child(self, scrape_item: ScrapeItem, link_str: str, *, embeds: bool = False) -> None:
        link_str_ = pre_process_child(link_str, embeds=embeds)
        if not link_str_:
            return None
        link = await self.get_absolute_link(link_str_)
        if not link:
            return None
        if self.is_thumbnail(link):
            link = self.thumbnail_to_img(link)
            if not link:
                return self.log.info(f"Skipping thumbnail: {link}")
        await self.handle_link(scrape_item, link)

    async def get_absolute_link(self, link: str | AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        absolute_link = link if type(link) is AbsoluteHttpURL else self.parse_url(clean_link_str(link))
        if is_confirmation_link(absolute_link):
            return await self.resolve_confirmation_link(absolute_link)
        return absolute_link

    @error_handling_wrapper
    async def resolve_confirmation_link(self, link: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        if url := link.query.get("url") or link.query.get("to"):
            url = base64.urlsafe_b64decode(b64_pad(url)).decode("utf-8")
            if url.startswith("https://"):
                return self.parse_url(url)

        soup = await self.request_soup(link)
        selector = self.SELECTORS.confirmation_button
        confirm_button = soup.select_one(selector.element)
        if not confirm_button:
            return None

        link_str: str = css.attr(confirm_button, selector.attribute)
        link_str = link_str.split('" class="link link--internal', 1)[0]
        new_link = self.parse_url(link_str)
        return await self.get_absolute_link(new_link)

    @error_handling_wrapper
    async def handle_internal_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL | None = None) -> None:
        link = link or scrape_item.url
        slug = link.name or link.parent.name
        if slug.isdigit():
            return await self.follow_redirect(scrape_item.create_new(link))

        await super().handle_internal_link(scrape_item, link)

    @classmethod
    def is_username_or_attachment(cls, link_obj: Tag) -> bool:
        if link_obj.select_one(".username"):
            return True
        try:
            if link_str := css.attr(link_obj, cls.SELECTORS.posts.links.element):
                return cls.is_attachment(link_str)
        except Exception:  # noqa: BLE001
            pass
        return False


def iter_links(links: Iterable[Tag], attribute: str) -> Iterable[str]:
    for link_tag in links:
        try:
            yield css.attr(link_tag, attribute)
        except Exception:  # noqa: BLE001, S112
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


async def check_is_not_last_page(response: ClientResponse, selectors: MessageBoardSelectors) -> bool:
    soup = BeautifulSoup(await response.text(), "html.parser")
    return not is_last_page(soup, selectors)


def is_last_page(soup: BeautifulSoup, selectors: MessageBoardSelectors) -> bool:
    try:
        last_page = css.select(soup, *selectors.last_page)
        current_page = css.select(soup, *selectors.current_page)
    except (AttributeError, IndexError, css.SelectorError):
        return True
    return current_page == last_page


def get_post_title(soup: BeautifulSoup, selectors: MessageBoardSelectors) -> str:
    try:
        title_block = css.select(soup, selectors.title.element)
        for trash in selectors.title_trash:
            css.decompose(title_block, trash)
    except (AttributeError, AssertionError, css.SelectorError) as e:
        raise ScrapeError(429, message="Invalid response from forum. You may have been rate limited") from e

    if title := " ".join(css.text(title_block).split()):
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
    return (
        "masked" in link.parts or "link-confirmation" in link.path or ("redirect" in link.parts and "to" in link.query)
    )


def pre_process_child(link_str: str, *, embeds: bool = False) -> str | None:
    assert isinstance(link_str, str)
    if embeds:
        link_str = extract_embed_url(link_str)

    if link_str and not is_blob_or_svg(link_str):
        return link_str
