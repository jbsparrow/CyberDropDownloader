# ruff : noqa: RUF009

from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass
from functools import cached_property, partial, singledispatchmethod
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import LoginError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.scraper.filters import set_return_value
from cyberdrop_dl.utils.data_enums_classes.url_objects import FORUM, FORUM_POST, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from bs4 import Tag

    from cyberdrop_dl.managers.manager import Manager


HTTP_URL_REGEX_STRS = [
    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}\\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)",
    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}\/[-a-zA-Z0-9@:%._\+~#=]*\/[-a-zA-Z0-9@:?&%._\+~#=]*",
]

HTTP_URL_PATTERNS = [re.compile(regex) for regex in HTTP_URL_REGEX_STRS]


@dataclass(frozen=True, slots=True)
class Selector:
    element: str
    attribute: str = ""


@dataclass(frozen=True, slots=True)
class PostSelectors(Selector):
    element: str = "div[class*=message-main]"
    attachments: Selector = Selector("section[class=message-attachments] a ", "href")
    content: Selector = Selector("div[class*=message-userContent]")
    date: Selector = Selector("time", "data-timestamp")
    embeds: Selector = Selector("span[data-s9e-mediaembed-iframe]", "data-s9e-mediaembed-iframe")
    iframe: Selector = Selector("iframe[class=saint-iframe]", "href")
    images: Selector = Selector("img[class*=bbImage]", "src")
    links: Selector = Selector("a", "href")
    number: Selector = Selector("li[class=u-concealed] a", "href")
    videos: Selector = Selector("video source", "src")


@dataclass(frozen=True, slots=True)
class XenforoSelectors:
    next_page: Selector = Selector("a[class*=pageNav-jump--next]", "href")
    posts: PostSelectors = PostSelectors()
    title: Selector = Selector("h1[class=p-title-value]")
    title_trash: Selector = Selector("span")
    quotes: Selector = Selector("blockquote")
    post_name: str = "post-"


@dataclass(frozen=True)
class ForumPost:
    soup: Tag
    selectors: PostSelectors
    title: str | None = None
    post_name: str = "post-"

    @cached_property
    def content(self) -> Tag:
        return self.soup.select_one(self.selectors.content.element)

    @cached_property
    def date(self) -> int | None:
        date = None
        with contextlib.suppress(AttributeError):
            date = int(self.content.select_one(self.selectors.date.element).get(self.selectors.date.attribute))
        return date

    @cached_property
    def number(self) -> int:
        if self.selectors.number.element == self.selectors.number.attribute:
            number = int(self.soup.get(self.selectors.number.element))
            return number
        number = self.soup.select_one(self.selectors.number.element)
        return int(number.get(self.selectors.number.attribute).split("/")[-1].split(self.post_name)[-1])

    @cached_property
    def id(self) -> int:
        return self.number


@dataclass(frozen=True, slots=True)
class ThreadInfo:
    name: str
    id_: int
    page: int
    post: int
    url: URL
    complete_url: URL


@dataclass(frozen=True, slots=True)
class ForumThreadPage:
    thread: ThreadInfo
    posts: Sequence[Tag]


class XenforoCrawler(Crawler):
    login_required = True
    selectors = XenforoSelectors()
    POST_NAME = "post-"
    PAGE_NAME = "page-"
    thread_url_part = "threads"

    def __init__(self, manager: Manager, site: str, folder_domain: str | None = None) -> None:
        super().__init__(manager, site, folder_domain)
        assert self.primary_base_domain, "Subclasses must override primary_base_domain"
        self.attachment_url_parts = ["attachments", "data"]
        self.attachment_url_hosts = ["smgmedia", "attachments.f95zone"]
        self.logged_in = False

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        if not self.logged_in:
            login_url = self.primary_base_domain / "login"
            await self.login_setup(login_url)

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if not self.logged_in and self.login_required:
            return
        scrape_item.url = self.pre_filter_link(scrape_item.url)
        if self.is_attachment(scrape_item.url):
            await self.handle_internal_link(scrape_item)
        elif self.thread_url_part in scrape_item.url.parts:
            await self.thread(scrape_item)
        elif any(p in scrape_item.url.parts for p in ("goto", "posts")):
            await self.redirect(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def redirect(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            _, url = await self.client.get_soup_and_return_url(self.domain, scrape_item.url, origin=scrape_item)  # type: ignore
        scrape_item.url = url
        self.manager.task_group.create_task(self.run(scrape_item))

    @error_handling_wrapper
    async def thread(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a forum thread."""
        scrape_item.set_type(FORUM, self.manager)
        thread = self.get_thread_info(scrape_item.url)
        title = None
        last_post_url = thread.url
        async for soup in self.thread_pager(scrape_item):
            if not title:
                title_block = soup.select_one(self.selectors.title.element)
                trash: list[Tag] = title_block.find_all(self.selectors.title_trash.element)
                for element in trash:
                    element.decompose()

                title = self.create_title(title_block.text.replace("\n", ""), thread_id=thread.id_)
                scrape_item.add_to_parent_title(title)

            posts = soup.select(self.selectors.posts.element)
            forum_thread_page = ForumThreadPage(thread, posts)
            continue_scraping, last_post_url = self.process_thread_page(scrape_item, forum_thread_page)
            if not continue_scraping:
                break

        await self.write_last_forum_post(thread.url, last_post_url)

    def process_thread_page(self, scrape_item: ScrapeItem, forum_page: ForumThreadPage) -> tuple[bool, URL]:
        continue_scraping = False
        create = partial(self.create_scrape_item, scrape_item)
        thread = forum_page.thread
        post_url = thread.url
        for post in forum_page.posts:
            current_post = ForumPost(post, selectors=self.selectors.posts, post_name=self.POST_NAME)
            continue_scraping, scrape_post = self.check_post_number(thread.post, current_post.number)
            date = current_post.date
            post_string = f"{self.POST_NAME}{current_post.number}"
            post_url = thread.url / post_string
            if scrape_post:
                new_scrape_item = create(thread.url, possible_datetime=date, add_parent=post_url)
                self.manager.task_group.create_task(self.post(new_scrape_item, current_post))
                scrape_item.add_children()

            if not continue_scraping:
                break
        return continue_scraping, post_url

    async def post(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        """Scrapes a post."""
        self.add_separate_post_title(scrape_item, post)
        scrape_item.set_type(FORUM_POST, self.manager)
        posts_scrapers = [self.attachments, self.embeds, self.images, self.links, self.videos]
        for scraper in posts_scrapers:
            await scraper(scrape_item, post)

    async def links(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        """Scrapes links from a post."""
        selector = post.selectors.links
        links = post.content.select(selector.element)
        links = [link for link in links if self.is_valid_post_link(link)]
        await self.process_children(scrape_item, links, selector.attribute)

    async def images(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        """Scrapes images from a post."""
        selector = post.selectors.images
        images = post.content.select(selector.element)
        await self.process_children(scrape_item, images, selector.attribute)

    async def videos(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        """Scrapes videos from a post."""
        selector = post.selectors.videos
        iframe_selector = post.selectors.iframe
        videos = post.content.select(selector.element)
        videos.extend(post.content.select(iframe_selector.element))
        await self.process_children(scrape_item, videos, selector.attribute)

    async def embeds(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        """Scrapes embeds from a post."""
        selector = post.selectors.embeds
        embeds = post.content.select(selector.element)
        await self.process_children(scrape_item, embeds, selector.attribute)

    async def attachments(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        """Scrapes attachments from a post."""
        selector = post.selectors.attachments
        attachments = post.content.select(selector.attribute)
        await self.process_children(scrape_item, attachments, selector.attribute)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def thread_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of forum thread pages."""
        page_url = scrape_item.url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select_one(self.selectors.next_page.element)
            yield soup
            if not next_page:
                break
            page_url_str: str = next_page.get(self.selectors.next_page.attribute)
            page_url = self.parse_url(page_url_str)
            page_url = self.pre_filter_link(page_url)

    async def process_children(self, scrape_item: ScrapeItem, links: list[Tag], selector: str | None) -> None:
        for link_obj in links:
            link_tag: Tag | str = link_obj.get(selector)
            if link_tag and not isinstance(link_tag, str):
                parent_simp_check = link_tag.parent.get("data-simp")
                if parent_simp_check and "init" in parent_simp_check:
                    continue

            link_str: str = link_tag or link_obj.get("href")
            if selector == self.selectors.posts.embeds.attribute:
                link_str: str = self.process_embed(link_tag)

            if not link_str or link_str.startswith("data:image/svg"):
                continue

            link = await self.get_absolute_link(link_str)
            link = self.filter_link(link)
            if not link:
                continue
            await self.handle_link(scrape_item, link)
            scrape_item.add_children()

    @singledispatchmethod
    def is_attachment(self, link: URL) -> bool:
        if not link:
            return False
        assert link.host
        parts = self.attachment_url_parts
        hosts = self.attachment_url_hosts
        return any(p in link.parts for p in parts) or any(h in link.host for h in hosts)

    @is_attachment.register
    def _(self, link_str: str) -> bool:
        if not link_str:
            return False
        link = self.parse_url(link_str)
        return self.is_attachment(link)

    @singledispatchmethod
    async def get_absolute_link(self, link: URL) -> URL | None:
        absolute_link = link
        if self.is_confirmation_link(link):
            absolute_link = await self.handle_confirmation_link(link)
        return absolute_link

    @get_absolute_link.register
    async def _(self, link: str) -> URL | None:
        link_str = link
        text_to_replace = [(".th.", "."), (".md.", "."), ("ifr", "watch")]
        for old, new in text_to_replace:
            link_str = link_str.replace(old, new)
        parsed_link = self.parse_url(link_str)
        return await self.get_absolute_link(parsed_link)

    async def handle_link(self, scrape_item: ScrapeItem, link: URL) -> None:
        if not link or link == self.primary_base_domain:
            return
        assert link.host
        new_scrape_item = self.create_scrape_item(scrape_item, link)
        if self.is_attachment(link):
            return await self.handle_internal_link(new_scrape_item)
        if self.primary_base_domain.host in link.host:  # type: ignore
            origin = scrape_item.parents[0]
            return log(f"Skipping nested thread URL {link} found on {origin}", 10)
        new_scrape_item.set_type(None, self.manager)
        self.handle_external_links(new_scrape_item)

    @error_handling_wrapper
    async def handle_internal_link(self, scrape_item: ScrapeItem) -> None:
        """Handles internal links."""
        filename, ext = get_filename_and_ext(scrape_item.url.name, forum=True)
        scrape_item.add_to_parent_title("Attachments")
        scrape_item.part_of_album = True
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_confirmation_link(self, link: URL, *, origin: ScrapeItem | None = None) -> URL | None:
        """Handles link confirmation."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, link, origin=origin)
        confirm_button = soup.select_one("a[class*=button--cta]")
        if not confirm_button:
            return
        link_str: str = confirm_button.get("href")
        link_str = link_str.split('" class="link link--internal', 1)[0]
        new_link = self.parse_url(link_str)
        return await self.get_absolute_link(new_link)

    def check_post_number(self, post_number: int, current_post_number: int) -> tuple[bool, bool]:
        """Checks if the program should scrape the current post.

        Returns (continue_scraping, scrape_post)"""
        scrape_single_forum_post = self.manager.config_manager.settings_data.download_options.scrape_single_forum_post
        scrape_post = continue_scraping = True
        if scrape_single_forum_post:
            if not post_number or post_number == current_post_number:
                continue_scraping = False
            else:
                scrape_post = False

        elif post_number and post_number > current_post_number:
            scrape_post = False

        return continue_scraping, scrape_post

    async def write_last_forum_post(self, thread_url: URL, last_post_url: URL | None) -> None:
        if not last_post_url or last_post_url == thread_url:
            return
        await self.manager.log_manager.write_last_post_log(last_post_url)

    def is_valid_post_link(self, link_obj: Tag) -> bool:
        is_image = link_obj.select_one("img")
        link_str: str = link_obj.get(self.selectors.posts.links.element)
        return not (is_image or self.is_attachment(link_str))

    def is_confirmation_link(self, link: URL) -> bool:
        return any(keyword in link.path for keyword in ("link-confirmation",))

    def process_embed(self, data: str) -> str | None:
        if not data:
            return
        data = data.replace(r"\/\/", "https://www.").replace("\\", "")
        embed = re.search(HTTP_URL_PATTERNS[0], data) or re.search(HTTP_URL_PATTERNS[1], data)
        return embed.group(0).replace("www.", "") if embed else data

    def pre_filter_link(self, link: URL) -> URL:
        return link

    def filter_link(self, link: URL | None) -> URL | None:
        return link

    """ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def login_setup(self, login_url: URL) -> None:
        host_cookies: dict = self.client.client_manager.cookies.filter_cookies(self.primary_base_domain)
        session_cookie = host_cookies.get("xf_user")
        session_cookie = session_cookie.value if session_cookie else None
        if session_cookie:
            self.logged_in = True
            return

        forums_auth_data = self.manager.config_manager.authentication_data.forums
        session_cookie = getattr(forums_auth_data, f"{self.domain}_xf_user_cookie")
        username = getattr(forums_auth_data, f"{self.domain}_username")
        password = getattr(forums_auth_data, f"{self.domain}_password")

        await self.forum_login(login_url, session_cookie, username, password)

        if not (self.login_required or self.logged_in):
            log(f"Scraping {self.folder_domain} without an account", 30)

    @error_handling_wrapper
    async def forum_login(self, login_url: URL, session_cookie: str, username: str, password: str) -> None:
        """Logs in to a forum."""

        attempt = 0
        retries = wait_time = 5
        manual_login = username and password
        missing_credentials = not (manual_login or session_cookie)
        if missing_credentials:
            msg = f"Login info wasn't provided for {self.folder_domain}"
            raise LoginError(message=msg)

        if session_cookie:
            cookies = {"xf_user": session_cookie}
            self.update_cookies(cookies)

        text, logged_in = await self.check_login_with_request(login_url)
        if logged_in:
            self.logged_in = True
            return

        credentials = {"login": username, "password": password, "_xfRedirect": str(self.primary_base_domain)}

        def prepare_login_data(resp_text) -> dict:
            soup = BeautifulSoup(resp_text, "html.parser")
            inputs = soup.select("form input")
            data: dict = {elem["name"]: elem["value"] for elem in inputs if elem.get("name") and elem.get("value")}
            return data | credentials

        while attempt < retries:
            with contextlib.suppress(TimeoutError):
                attempt += 1
                await set_return_value(str(login_url), False, pop=False)
                await set_return_value(str(login_url / "login"), False, pop=False)
                await asyncio.sleep(wait_time)
                login_data = prepare_login_data(text)
                await self.client.post_data(self.domain, login_url / "login", data=login_data, req_resp=False)
                await asyncio.sleep(wait_time)
                text, logged_in = await self.check_login_with_request(login_url)
                if logged_in:
                    self.logged_in = True
                    return

        msg = f"Failed to login on {self.folder_domain} after {retries} attempts"
        raise LoginError(message=msg)

    async def check_login_with_request(self, login_url: URL) -> tuple[str, bool]:
        text = await self.client.get_text(self.domain, login_url)
        return text, any(p in text for p in ('<span class="p-navgroup-user-linkText">', "You are already logged in."))

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def get_thread_info(self, url: URL) -> ThreadInfo:
        name_index = url.parts.index(self.thread_url_part) + 1
        name, id_ = get_thread_name_and_id(url, name_index)
        thread_url = get_thread_canonical_url(url, name_index)
        page, post = get_thread_page_and_post(url, name_index, self.PAGE_NAME, self.POST_NAME)
        return ThreadInfo(name, id_, page, post, thread_url, url)


def get_thread_name_and_id(url: URL, thread_name_index: int) -> tuple[str, int]:
    thread_name, thread_id_str = url.parts[thread_name_index].rsplit(".", 1)
    thread_id = int(thread_id_str)
    return thread_name, thread_id


def get_thread_canonical_url(url: URL, thread_name_index: int) -> URL:
    new_parts = url.parts[1 : thread_name_index + 1]
    new_path = "/".join(new_parts)
    thread_url = url.with_path(new_path).with_fragment(None).with_query(None)
    return thread_url


def get_thread_page_and_post(url: URL, thread_name_index: int, page_name: str, post_name: str) -> tuple[int, int]:
    post_or_page_index = thread_name_index + 1
    extra_parts = set(url.parts[post_or_page_index:])
    sections = {url.fragment} if url.fragment else set()
    sections.update(extra_parts)

    def find_number(search_value: str) -> int:
        for sec in sections:
            if search_value in sec:
                return int(sec.replace(search_value, "").strip())
        return 0

    post_number = find_number(post_name)
    page_number = find_number(page_name)
    return page_number, post_number
