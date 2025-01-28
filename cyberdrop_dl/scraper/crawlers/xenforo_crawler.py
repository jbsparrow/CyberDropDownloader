from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass, field
from functools import partial, singledispatchmethod
from typing import TYPE_CHECKING, NamedTuple

from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import LoginError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.scraper.filters import set_return_value
from cyberdrop_dl.utils.data_enums_classes.url_objects import FORUM, FORUM_POST, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import Tag

    from cyberdrop_dl.managers.manager import Manager


HTTP_URL_REGEX_STRS = [
    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}\\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)",
    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}\/[-a-zA-Z0-9@:%._\+~#=]*\/[-a-zA-Z0-9@:?&%._\+~#=]*",
]

HTTP_URL_PATTERNS = [re.compile(regex) for regex in HTTP_URL_REGEX_STRS]


@dataclass(frozen=True)
class Selector:
    element: str
    attribute: str = None


@dataclass(frozen=True)
class PostSelectors(Selector):
    element: str = "div[class*=message-main]"
    attachments: Selector = field(default=Selector("section[class=message-attachments] a ", "href"))
    content: Selector = field(default=Selector("div[class*=message-userContent]", None))
    date: Selector = field(default=Selector("time", "data-timestamp"))
    embeds: Selector = field(default=Selector("span[data-s9e-mediaembed-iframe]", "data-s9e-mediaembed-iframe"))
    iframe: Selector = field(default=Selector("iframe[class=saint-iframe]", "href"))
    images: Selector = field(default=Selector("img[class*=bbImage]", "src"))
    links: Selector = field(default=Selector("a", "href"))
    number: Selector = field(default=Selector("li[class=u-concealed] a", "href"))
    videos: Selector = field(default=Selector("video source", "src"))


@dataclass(frozen=True)
class XenforoSelectors:
    next_page: Selector = field(default=Selector("a[class*=pageNav-jump--next]", "href"))
    posts: PostSelectors = field(default=PostSelectors())
    title: Selector = field(default=Selector("h1[class=p-title-value]", None))
    title_trash: Selector = field(default=Selector("span", None))
    quotes: Selector = field(default=Selector("blockquote", None))
    post_name: str = "post-"


@dataclass(frozen=True)
class ForumPost:
    soup: Tag
    selectors: PostSelectors
    title: str | None = None
    post_name: str = "post-"

    @property
    def content(self) -> Tag:
        return self.soup.select_one(self.selectors.content.element)

    @property
    def date(self):
        date = None
        with contextlib.suppress(AttributeError):
            date = int(self.content.select_one(self.selectors.date.element).get(self.selectors.date.attribute))
        return date

    @property
    def number(self):
        if self.selectors.number.element == self.selectors.number.attribute:
            number = int(self.soup.get(self.selectors.number.element))
            return number
        number = self.soup.select_one(self.selectors.number.element)
        return int(number.get(self.selectors.number.attribute).split("/")[-1].split(self.post_name)[-1])

    @property
    def id(self):
        return self.number


class XenforoCrawler(Crawler):
    login_required = True
    primary_base_domain = None
    selectors = XenforoSelectors()
    POST_NAME = "post-"
    PAGE_NAME = "page-"
    thread_url_part = "threads"

    def __init__(self, manager: Manager, site: str, folder_domain: str | None = None) -> None:
        super().__init__(manager, site, folder_domain)
        self.primary_base_domain = self.primary_base_domain or URL(f"https://{site}")
        self.attachment_url_parts = ["attachments", "data"]
        self.attachment_url_hosts = ["smgmedia", "attachments.f95zone"]
        self.logged_in = False

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        if not self.logged_in:
            await self.try_login()

    async def pre_filter_link(self, link: URL) -> URL:
        return link

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if not self.logged_in and self.login_required:
            return
        scrape_item.url = await self.pre_filter_link(scrape_item.url)
        if self.is_attachment(scrape_item.url):
            await self.handle_internal_link(scrape_item.url, scrape_item)
        elif self.thread_url_part in scrape_item.url.parts:
            await self.thread(scrape_item)
        elif any(p in scrape_item.url.parts for p in ("goto", "posts")):
            await self.handle_redirect(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def handle_redirect(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            _, url = await self.client.get_soup_and_return_url(self.domain, scrape_item.url, origin=scrape_item)
        scrape_item.url = url
        self.manager.task_group.create_task(self.run(scrape_item))

    async def try_login(self) -> None:
        login_url = self.primary_base_domain / "login"
        host_cookies: dict = self.client.client_manager.cookies.filter_cookies(self.primary_base_domain)
        session_cookie = host_cookies.get("xf_user")
        session_cookie = session_cookie.value if session_cookie else None
        forums_auth_data = self.manager.config_manager.authentication_data.forums
        if session_cookie:
            self.logged_in = True
            return

        session_cookie = getattr(forums_auth_data, f"{self.domain}_xf_user_cookie")
        username = getattr(forums_auth_data, f"{self.domain}_username")
        password = getattr(forums_auth_data, f"{self.domain}_password")

        if session_cookie or (username and password):
            try:
                await self.forum_login(login_url, session_cookie, username, password)
            except LoginError:
                if self.login_required:
                    raise

        if not self.logged_in:
            msg = f"{self.folder_domain} login failed. "
            if not self.login_required:
                msg += "Scraping without an account."
            log(msg, 40)

    @error_handling_wrapper
    async def thread(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a forum thread."""
        scrape_item.set_type(FORUM, self.manager)
        thread = self.get_thread_info(scrape_item.url)
        title = last_scraped_post_number = None
        async for soup in self.thread_pager(scrape_item):
            if not title:
                title_block = soup.select_one(self.selectors.title.element)
                trash: list[Tag] = title_block.find_all(self.selectors.title_trash.element)
                for element in trash:
                    element.decompose()

                title = self.create_title(title_block.text.replace("\n", ""), thread_id=thread.id_)

            scrape_item.add_to_parent_title(title)
            posts = soup.select(self.selectors.posts.element)
            continue_scraping = False
            create = partial(self.create_scrape_item, scrape_item)
            for post in posts:
                current_post = ForumPost(post, selectors=self.selectors.posts, post_name=self.POST_NAME)
                last_scraped_post_number = current_post.number
                scrape_post, continue_scraping = self.check_post_number(thread.post, current_post.number)
                date = current_post.date
                if scrape_post:
                    post_string = f"{self.POST_NAME}{current_post.number}"
                    parent_url = thread.url / post_string
                    new_scrape_item = create(thread.url, possible_datetime=date, add_parent=parent_url)
                    self.manager.task_group.create_task(self.post(new_scrape_item, current_post))
                    scrape_item.add_children()

                if not continue_scraping:
                    break
            if not continue_scraping:
                break

        await self.write_last_forum_post(thread.url, last_scraped_post_number)

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

    def process_embed(self, data: str) -> str | None:
        if not data:
            return
        data = data.replace(r"\/\/", "https://www.").replace("\\", "")
        embed = re.search(HTTP_URL_PATTERNS[0], data) or re.search(HTTP_URL_PATTERNS[1], data)
        return embed.group(0).replace("www.", "") if embed else data

    async def filter_link(self, link: URL | None) -> URL | None:
        return link

    async def process_children(self, scrape_item: ScrapeItem, links: list[Tag], selector: str) -> None:
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
            link = await self.filter_link(link)
            if not link:
                continue
            await self.handle_link(scrape_item, link)
            scrape_item.add_children()

    @singledispatchmethod
    def is_attachment(self, link: URL) -> bool:
        if not link:
            return False
        parts = self.attachment_url_parts
        hosts = self.attachment_url_hosts
        return any(part in link.parts for part in parts) or any(host in link.host for host in hosts)

    @is_attachment.register
    def _(self, link_str: str) -> bool:
        if not link_str:
            return False
        link = self.parse_url(link_str)
        return self.is_attachment(link)

    async def handle_link(self, scrape_item: ScrapeItem, link: URL) -> None:
        if not link:
            return
        try:
            if self.domain not in link.host:
                new_scrape_item = self.create_scrape_item(scrape_item, link)
                new_scrape_item.reset_childen()
                self.handle_external_links(new_scrape_item)
            elif self.is_attachment(link):
                await self.handle_internal_link(link, scrape_item)
            else:
                log(f"Unknown link type: {link}", 30)
        except TypeError:
            log(f"Scrape Failed: encountered while handling {link}", 40)

    async def handle_internal_link(self, link: URL, scrape_item: ScrapeItem) -> None:
        """Handles internal links."""
        filename, ext = get_filename_and_ext(link.name, True)
        new_scrape_item = self.create_scrape_item(scrape_item, link, "Attachments", part_of_album=True)
        await self.handle_file(link, new_scrape_item, filename, ext)

    def is_confirmation_link(self, link: URL) -> bool:
        return any(keyword in link.path for keyword in ("link-confirmation",))

    @error_handling_wrapper
    async def handle_confirmation_link(self, link: URL, *, origin: ScrapeItem | None = None) -> URL | None:
        """Handles link confirmation."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, link, origin=origin)
        confirm_button = soup.select_one("a[class*=button--cta]")
        if not confirm_button:
            return
        link_str: str = confirm_button.get("href")
        return self.parse_url(link_str)

    async def write_last_forum_post(self, thread_url: URL, post_number: int | None) -> None:
        if not post_number:
            return
        post_string = f"{self.POST_NAME}{post_number}"
        last_post_url = thread_url / post_string
        await self.manager.log_manager.write_last_post_log(last_post_url)

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
            page_url = await self.pre_filter_link(page_url)

    @error_handling_wrapper
    async def forum_login(self, login_url: URL, session_cookie: str, username: str, password: str) -> None:
        """Logs into a forum."""

        attempt = 0

        text, logged_in = await self.check_login_with_request(login_url)
        if logged_in:
            return

        wait_time: int = 5

        if not ((username and password) or session_cookie):
            log(f"Login wasn't provided for {login_url.host}", 40)
            raise LoginError(message="Login wasn't provided")

        if session_cookie:
            self.client.client_manager.cookies.update_cookies(
                {"xf_user": session_cookie},
                response_url=self.primary_base_domain,
            )

        credentials = {"login": username, "password": password, "_xfRedirect": str(self.primary_base_domain)}

        def prepare_login_data(resp_text) -> dict:
            soup = BeautifulSoup(resp_text, "html.parser")
            inputs = soup.select("form input")
            data: dict = {elem["name"]: elem["value"] for elem in inputs if elem.get("name") and elem.get("value")}
            return data | credentials

        while attempt < 5:
            try:
                attempt += 1
                assert login_url.host
                await set_return_value(str(login_url), False, pop=False)
                await set_return_value(str(login_url / "login"), False, pop=False)
                await asyncio.sleep(wait_time)
                data = prepare_login_data(text)
                await self.client.post_data(self.domain, login_url / "login", data=data, req_resp=False)
                await asyncio.sleep(wait_time)
                text, logged_in = await self.check_login_with_request(login_url)
                if logged_in:
                    self.logged_in = True
                    return

            except TimeoutError:
                continue

        raise LoginError(message="Failed to login after 5 attempts")

    async def check_login_with_request(self, login_url: URL) -> tuple[str, bool]:
        text = await self.client.get_text(self.domain, login_url)
        return text, any(p in text for p in ('<span class="p-navgroup-user-linkText">', "You are already logged in."))

    def is_valid_post_link(self, link_obj: Tag) -> bool:
        is_image = link_obj.select_one("img")
        link_str: str = link_obj.get(self.selectors.posts.links.element)
        return not (is_image or self.is_attachment(link_str))

    @singledispatchmethod
    async def get_absolute_link(self, link: URL) -> URL | None:
        absolute_link = link
        if self.is_confirmation_link(link):
            absolute_link = await self.handle_confirmation_link(link)
        return absolute_link

    @get_absolute_link.register
    async def _(self, link: str) -> URL | None:
        parsed_link = None
        link_str: str = link.replace(".th.", ".").replace(".md.", ".").replace("ifr", "watch")
        parsed_link = self.parse_url(link_str)
        return await self.get_absolute_link(parsed_link)

    def get_thread_info(self, url: URL) -> ThreadInfo:
        name_index = url.parts.index(self.thread_url_part) + 1
        name, id_ = get_thread_name_and_id(url, name_index)
        thread_url = get_thread_canonical_url(url, name_index)
        page, post = get_thread_page_and_post(url, name_index, self.PAGE_NAME, self.POST_NAME)

        return ThreadInfo(name, id_, page, post, thread_url, url)


class ThreadInfo(NamedTuple):
    name: str
    id_: int
    page: int
    post: int
    url: URL
    complete_url: URL


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
