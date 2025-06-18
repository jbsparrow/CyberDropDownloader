# ruff : noqa: RUF009

from __future__ import annotations

import asyncio
import dataclasses
import re
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup, Tag

from cyberdrop_dl.crawlers._forum import ForumCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import LoginError, MaxChildrenError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dates import TimeStamp
from cyberdrop_dl.utils.utilities import (
    error_handling_wrapper,
    get_text_between,
    is_absolute_http_url,
    is_blob_or_svg,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from aiohttp_client_cache.response import AnyResponse

    from cyberdrop_dl.crawlers.crawler import SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


HTTP_URL_REGEX = re.compile(r"https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,12}\b([-a-zA-Z0-9@:%_+.~#?&/=]*)")
LINK_TRASH_MAPPING = {
    ".th.": ".",
    ".md.": ".",
    "ifr": "watch",
}

Selector = css.CssAttributeSelector

LAST_PAGE_SELECTOR = Selector("li.pageNav-page a:last-of-type", "href")
CURRENT_PAGE_SELECTOR = Selector("li.pageNav-page.pageNav-page--current a", "href")


@dataclasses.dataclass(frozen=True, slots=True)
class PostSelectors:
    article: str = "article.message[id*=post]"  # the entire html of the post (comments, attachments, user avatar, signature, etc...)

    attachments: Selector = Selector(".message-attachments a[href]", "href")
    content: Selector = Selector(".message-userContent")  # text, links and images (NO attachments)
    date: Selector = Selector("time", "data-timestamp")
    embeds: Selector = Selector("iframe", "src")
    id: Selector = Selector(".u-concealed a[href]", "href")  # TODO: This needs a better selector
    images: Selector = Selector("img.bbImage", "src")
    lazy_load_embeds: Selector = Selector('[class*=iframe][onclick*="loadMedia(this, \'//"]', "onclick")
    links: Selector = Selector(":any-link", "href")
    videos: Selector = Selector("video source", "src")


@dataclasses.dataclass(frozen=True, slots=True)
class XenforoSelectors:
    confirmation_button: Selector = Selector("a[class*=button--cta][href]", "href")
    next_page: Selector = Selector("a[class*=pageNav-jump--next][href]", "href")
    posts: PostSelectors = PostSelectors()
    quotes: Selector = Selector("blockquote")
    title_trash: Selector = Selector("span")
    title: Selector = Selector("h1[class*=p-title-value]")
    last_page: Selector = LAST_PAGE_SELECTOR
    current_page: Selector = CURRENT_PAGE_SELECTOR


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class ForumPost:
    id: int
    date: TimeStamp
    article: Tag = dataclasses.field(compare=False)
    content: Tag = dataclasses.field(compare=False)

    @staticmethod
    def new(article: Tag, selectors: PostSelectors, post_name: str = "post") -> ForumPost:
        content = css.select_one(article, selectors.content.element)
        date = TimeStamp(int(css.select_one_get_attr(article, *selectors.date)))
        if selectors.id.element == selectors.id.attribute:
            post_id = int(css.get_attr(article, selectors.id.element))
        else:
            id_str = css.select_one_get_attr(article, *selectors.id)
            post_id = int(id_str.rsplit(post_name, 1)[-1].replace("-", ""))
        return ForumPost(post_id, date, article, content)


@dataclasses.dataclass(frozen=True, slots=True)
class Thread:
    id: int
    name: str
    page: int
    post_id: int | None
    url: AbsoluteHttpURL


DEFAULT_XF_SELECTORS = XenforoSelectors()
KNOWN_THREAD_PART_NAMES = "thread", "topic", "tema"
KNOWN_THREAD_PART_NAMES = [f"{part}s" for part in KNOWN_THREAD_PART_NAMES]


class XenforoCrawler(ForumCrawler, is_abc=True):
    XF_ATTACHMENT_URL_PARTS = "attachments", "data", "uploads"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Attachments": tuple(f"/{name}/..." for name in XF_ATTACHMENT_URL_PARTS),
        "Threads": (
            "/threads/<thread_name>",
            "/posts/<post_id>",
            "/goto/<post_id>",
        ),
    }
    SUPPORTS_THREAD_RECURSION: ClassVar[bool] = True
    XF_SELECTORS = DEFAULT_XF_SELECTORS
    XF_POST_URL_PART_NAME = "post-"
    XF_PAGE_URL_PART_NAME = "page-"
    XF_THREAD_URL_PART = "threads"
    XF_USER_COOKIE_NAME = "xf_user"
    XF_ATTACHMENT_HOSTS = "smgmedia", "attachments.f95zone"
    login_required = True

    def __post_init__(self) -> None:
        self.scraped_threads = set()

    async def async_startup(self) -> None:
        if not self.logged_in:
            login_url = self.PRIMARY_URL / "login"
            await self.login_setup(login_url)

        self.register_cache_filter(self.PRIMARY_URL, check_is_not_last_page)

    def get_filename_and_ext(self, filename: str) -> tuple[str, str]:
        return super().get_filename_and_ext(filename, forum=True)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if not self.logged_in and self.login_required:
            return
        url = self.pre_filter_link(str(scrape_item.url))
        scrape_item.url = self.parse_url(url)
        if self.is_attachment(scrape_item.url):
            return await self.handle_internal_link(scrape_item)
        if is_confirmation_link(scrape_item.url):
            return await self.follow_confirmation_link(scrape_item)

        thread_part_index = len(self.PRIMARY_URL.parts)
        match scrape_item.url.parts[thread_part_index:]:
            case [thread_part, thread_name_and_id, *_] if thread_part in KNOWN_THREAD_PART_NAMES:
                return await self.thread(scrape_item, thread_name_and_id)
            case ["goto" | "posts", *_]:
                return await self.follow_redirect_w_get(scrape_item)

        raise ValueError

    async def follow_confirmation_link(self, scrape_item: ScrapeItem) -> None:
        url = await self.resolve_confirmation_link(scrape_item.url)
        if url:  # If there was an error, this will be None
            scrape_item.url = url
            # This could end up back in here if the URL goes to another thread
            return self.handle_external_links(scrape_item)

    @error_handling_wrapper
    async def follow_redirect_w_get(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            response, _ = await self.client._get_response_and_soup(self.DOMAIN, scrape_item.url)
        assert is_absolute_http_url(response.url)
        scrape_item.url = response.url
        self.manager.task_group.create_task(self.run(scrape_item))

    @error_handling_wrapper
    async def follow_redirect_w_head(self, scrape_item: ScrapeItem) -> None:
        head = await self.client.get_head(self.DOMAIN, scrape_item.url)
        redirect = head.get("location")
        if not redirect:
            raise ScrapeError(422)
        scrape_item.url = self.parse_url(redirect)
        self.manager.task_group.create_task(self.run(scrape_item))

    async def forum(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    @error_handling_wrapper
    async def thread(self, scrape_item: ScrapeItem, thread_name_and_id: str) -> None:
        scrape_item.setup_as_forum("")
        thread = parse_thread(
            scrape_item.url, thread_name_and_id, self.XF_PAGE_URL_PART_NAME, self.XF_POST_URL_PART_NAME
        )
        if thread.url in self.scraped_threads:
            return

        scrape_item.parent_threads.add(thread.url)
        if self.scrape_single_forum_post and not thread.post_id:
            msg = "`--scrape-single-forum-post` is `True`, but the provided URL has no post id"
            raise ScrapeError("User Error", msg)

        title: str = ""
        self.scraped_threads.add(thread.url)
        last_post_url = thread.url
        async for soup in self.thread_pager(scrape_item):
            if not title:
                try:
                    title = self.create_title(get_post_title(soup, self.XF_SELECTORS), thread_id=thread.id)
                except ScrapeError as e:
                    self.log_debug("Got an unprocessable soup", 40, exc_info=e)
                    raise
                scrape_item.add_to_parent_title(title)

            continue_scraping, last_post_url = self.process_thread_page(scrape_item, thread, soup)
            if not continue_scraping:
                break

        await self.write_last_forum_post(thread.url, last_post_url)

    def process_thread_page(
        self, scrape_item: ScrapeItem, thread: Thread, soup: BeautifulSoup
    ) -> tuple[bool, AbsoluteHttpURL]:
        continue_scraping = False
        post_url = thread.url
        for article in soup.select(self.XF_SELECTORS.posts.article):
            current_post = ForumPost.new(article, self.XF_SELECTORS.posts, self.XF_POST_URL_PART_NAME)
            continue_scraping, scrape_this_post = check_post_id(
                thread.post_id, current_post.id, self.scrape_single_forum_post
            )
            if scrape_this_post:
                post_url = thread.url / f"{self.XF_POST_URL_PART_NAME}{current_post.id}"
                new_scrape_item = scrape_item.create_new(
                    thread.url, possible_datetime=current_post.date, add_parent=post_url
                )
                self.manager.task_group.create_task(self.post(new_scrape_item, current_post))
                try:
                    scrape_item.add_children()
                except MaxChildrenError:
                    break

            if not continue_scraping:
                break
        return continue_scraping, post_url

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        scrape_item.setup_as_post("")
        post_title = self.create_separate_post_title(None, str(post.id), post.date)
        scrape_item.add_to_parent_title(post_title)
        for scraper in (
            self._attachments,
            self._embeds,
            self._images,
            self._links,
            self._videos,
            self._lazy_load_embeds,
        ):
            await scraper(scrape_item, post)

    async def _links(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        selector = self.XF_SELECTORS.posts.links
        links = post.content.select(selector.element)
        links = [link for link in links if self.is_not_image_or_attachment(link)]
        await self.process_children(scrape_item, links, selector.attribute)

    async def _images(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        selector = self.XF_SELECTORS.posts.images
        images = post.content.select(selector.element)
        await self.process_children(scrape_item, images, selector.attribute)

    async def _videos(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        selector = self.XF_SELECTORS.posts.videos
        videos = post.content.select(selector.element)
        await self.process_children(scrape_item, videos, selector.attribute)

    async def _embeds(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        selector = self.XF_SELECTORS.posts.embeds
        embeds = post.content.select(selector.element)
        await self.process_children(scrape_item, embeds, selector.attribute, embeds=True)

    async def _attachments(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        selector = self.XF_SELECTORS.posts.attachments
        attachments = post.article.select(selector.element)
        await self.process_children(scrape_item, attachments, selector.attribute)

    async def _lazy_load_embeds(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        selector = self.XF_SELECTORS.posts.lazy_load_embeds
        for redgif in css.iselect(post.content, selector.element):
            link_str = get_text_between(css.get_attr(redgif, selector.attribute), "loadMedia(this, '", "')")
            await self.process_child(scrape_item, link_str, embeds=True)

    async def thread_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        async for soup in self._web_pager(scrape_item.url, self.get_next_page):
            yield soup

    def get_next_page(self, soup: BeautifulSoup) -> str | None:
        if next_page := css.select_one_get_attr_or_none(soup, *self.XF_SELECTORS.next_page):
            return self.pre_filter_link(next_page)

    @error_handling_wrapper
    async def process_children(
        self, scrape_item: ScrapeItem, links: list[Tag], attribute: str, *, embeds: bool = False
    ) -> None:
        for link_tag in links:
            if link_str := css.get_attr_no_error(link_tag, attribute):
                await self.process_child(scrape_item, link_str, embeds=embeds)

    @error_handling_wrapper
    async def process_child(self, scrape_item: ScrapeItem, link_str: str, *, embeds: bool = False) -> None:
        link_str_ = pre_process_child(link_str, embeds)
        if not link_str_:
            return
        link = await self.get_absolute_link(link_str_)
        link = self.filter_link(link)
        if not link:
            return
        await self.handle_link(scrape_item, link)

    def is_attachment(self, link: AbsoluteHttpURL | str) -> bool:
        if not link:
            return False
        if isinstance(link, str):
            link = self.parse_url(link)
        by_parts = len(link.parts) > 2 and any(p in link.parts for p in self.XF_ATTACHMENT_URL_PARTS)
        by_host = any(host in link.host for host in self.XF_ATTACHMENT_HOSTS)
        return by_parts or by_host

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
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, link)
        selector = self.XF_SELECTORS.confirmation_button
        confirm_button = soup.select_one(selector.element)
        if not confirm_button:
            return
        link_str: str = css.get_attr(confirm_button, selector.attribute)
        link_str = link_str.split('" class="link link--internal', 1)[0]
        new_link = self.parse_url(link_str)
        return await self.get_absolute_link(new_link)

    async def handle_internal_link(self, scrape_item: ScrapeItem) -> None:
        """Handles internal links."""
        slug = scrape_item.url.name or scrape_item.url.parent.name
        if slug.isdigit():
            return await self.follow_redirect_w_head(scrape_item)

        return await super().handle_internal_link(scrape_item)

    def is_not_image_or_attachment(self, link_obj: Tag) -> bool:
        is_image = link_obj.select_one("img")
        if link_str := css.get_attr_no_error(link_obj, self.XF_SELECTORS.posts.links.element):
            return not (is_image or self.is_attachment(link_str))
        return not is_image

    def pre_filter_link(self, link: str) -> str:
        return link

    def filter_link(self, link: AbsoluteHttpURL | None) -> AbsoluteHttpURL | None:
        return link

    @error_handling_wrapper
    async def login_setup(self, login_url: AbsoluteHttpURL) -> None:
        host_cookies: dict = self.client.client_manager.cookies.filter_cookies(self.PRIMARY_URL)
        session_cookie = host_cookies.get(self.XF_USER_COOKIE_NAME)
        session_cookie = session_cookie.value if session_cookie else None
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

    @error_handling_wrapper
    async def xf_login(self, login_url: AbsoluteHttpURL, session_cookie: str, username: str, password: str) -> None:
        """Logs in to a forum."""
        manual_login = username and password
        missing_credentials = not (manual_login or session_cookie)
        if missing_credentials:
            msg = f"Login info wasn't provided for {self.FOLDER_DOMAIN}"
            raise LoginError(message=msg)

        if session_cookie:
            cookies = {"xf_user": session_cookie}
            self.update_cookies(cookies)

        credentials = {"login": username, "password": password, "_xfRedirect": str(self.PRIMARY_URL)}
        await self.xf_try_login(login_url, credentials, retries=5)

    async def xf_try_login(
        self,
        login_url: AbsoluteHttpURL,
        credentials: dict[str, str],
        retries: int,
        wait_time: int | None = None,
    ) -> None:
        # Try from cookies
        text, logged_in = await self.check_login_with_request(login_url)
        if logged_in:
            self.logged_in = True
            return

        wait_time = wait_time or retries
        attempt = 0
        while attempt < retries:
            try:
                attempt += 1
                await asyncio.sleep(wait_time)
                data = parse_login_form(text) | credentials
                _ = await self.client._post_data(self.DOMAIN, login_url / "login", data=data, cache_disabled=True)
                await asyncio.sleep(wait_time)
                text, logged_in = await self.check_login_with_request(login_url)
                if logged_in:
                    self.logged_in = True
                    return
            except TimeoutError:
                continue
        msg = f"Failed to login on {self.FOLDER_DOMAIN} after {retries} attempts"
        raise LoginError(message=msg)

    async def check_login_with_request(self, login_url: AbsoluteHttpURL) -> tuple[str, bool]:
        text = await self.client.get_text(self.DOMAIN, login_url, cache_disabled=True)
        return text, any(p in text for p in ('<span class="p-navgroup-user-linkText">', "You are already logged in."))


def parse_thread(url: AbsoluteHttpURL, thread_name_and_id: str, page_part_name: str, post_part_name: str) -> Thread:
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
                return int(sec.replace(search_value, "").replace("-", "").strip())

    post_id = find_number(post_name)
    page_number = find_number(page_name) or 1
    return page_number, post_id


async def check_is_not_last_page(response: AnyResponse) -> bool:
    soup = BeautifulSoup(await response.text(), "html.parser")
    return not is_last_page(soup)


def is_last_page(soup: BeautifulSoup) -> bool:
    try:
        last_page = css.select_one_get_attr(soup, *LAST_PAGE_SELECTOR)
        current_page = css.select_one_get_attr(soup, *CURRENT_PAGE_SELECTOR)
    except (AttributeError, IndexError, css.SelectorError):
        return True
    return current_page == last_page


def get_post_title(soup: BeautifulSoup, selectors: XenforoSelectors) -> str:
    try:
        title_block = css.select_one(soup, selectors.title.element)
        trash = title_block.select(selectors.title_trash.element)
        for element in trash:
            element.decompose()
    except (AttributeError, AssertionError, css.SelectorError) as e:
        raise ScrapeError(429, message="Invalid response from forum. You may have been rate limited") from e

    if title := " ".join(css.get_text(title_block).split()):
        return title
    raise ScrapeError(422)


def extract_embed_url(embed_str: str) -> str:
    embed_str = embed_str.replace(r"\/\/", "https://www.").replace("\\", "")
    if match := re.search(HTTP_URL_REGEX, embed_str):
        return match.group(0).replace("www.", "")
    return embed_str


# TODO: move to parse_url
def clean_link_str(link: str) -> str:
    for old, new in LINK_TRASH_MAPPING.items():
        link = link.replace(old, new)
    return link


def parse_login_form(resp_text: str) -> dict[str, str]:
    soup = BeautifulSoup(resp_text, "html.parser")
    inputs = soup.select("form:first-of-type input")
    data = {
        name: value
        for elem in inputs
        if (name := css.get_attr_or_none(elem, "name")) and (value := css.get_attr_or_none(elem, "value"))
    }
    if data:
        return data
    raise ScrapeError(422)


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

    assert not scrape_single_forum_post  # We should have raised an exception early
    return True, True


def pre_process_child(link_str: str, embeds: bool = False) -> str | None:
    assert isinstance(link_str, str)
    if embeds:
        link_str = extract_embed_url(link_str)

    if link_str and not is_blob_or_svg(link_str):
        return link_str
