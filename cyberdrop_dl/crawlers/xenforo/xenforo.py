# ruff : noqa: RUF009

from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass
from functools import cached_property, singledispatchmethod
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, Tag
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.data_structures.url_objects import FORUM, ScrapeItem
from cyberdrop_dl.exceptions import InvalidURLError, LoginError, ScrapeError
from cyberdrop_dl.utils.logger import log, log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, remove_trailing_slash

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from aiohttp_client_cache.response import AnyResponse

    from cyberdrop_dl.managers.manager import Manager

HTTP_URL_REGEX_STR = r"https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,12}\b([-a-zA-Z0-9@:%_+.~#?&/=]*)"
HTTP_URL_REGEX = re.compile(HTTP_URL_REGEX_STR)


FINAL_PAGE_SELECTOR = "li.pageNav-page a"
CURRENT_PAGE_SELECTOR = "li.pageNav-page.pageNav-page--current a"


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
    post_name: str = "post-"

    @cached_property
    def content(self) -> Tag:
        return self.soup.select_one(self.selectors.content.element)  # type: ignore

    @cached_property
    def date(self) -> int | None:
        date_tag = self.content.select_one(self.selectors.date.element)
        date_str: str | None = date_tag.get(self.selectors.date.attribute) if date_tag else None  # type: ignore
        if not date_str:
            return
        return int(date_str)

    @cached_property
    def number(self) -> int:
        if self.selectors.number.element == self.selectors.number.attribute:
            number_str: str = self.soup.get(self.selectors.number.element)  # type: ignore
            return int(number_str)

        number_tag = self.soup.select_one(self.selectors.number.element)
        number_str: str = number_tag.get(self.selectors.number.attribute)  # type: ignore
        return int(number_str.split("/")[-1].split(self.post_name)[-1])


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
    session_cookie_name = "xf_user"

    def __init__(self, manager: Manager, site: str, folder_domain: str | None = None) -> None:
        super().__init__(manager, site, folder_domain)
        assert self.primary_base_domain, "Subclasses must override primary_base_domain"
        self.attachment_url_parts = ["attachments", "data"]
        self.attachment_url_hosts = ["smgmedia", "attachments.f95zone"]
        self.logged_in = False
        self.scraped_threads = set()

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        if not self.logged_in:
            login_url = self.primary_base_domain / "login"
            await self.login_setup(login_url)

        async def is_not_last_page(response: AnyResponse):
            soup = BeautifulSoup(await response.text(), "html.parser")
            try:
                last_page = int(soup.select(FINAL_PAGE_SELECTOR)[-1].text.split("page-")[-1])
                current_page = int(soup.select(CURRENT_PAGE_SELECTOR)[0].text.split("page-")[-1])
            except (AttributeError, IndexError):
                return False
            return current_page != last_page

        self.register_cache_filter(self.primary_base_domain, is_not_last_page)

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if not self.logged_in and self.login_required:
            return
        scrape_item.url = self.pre_filter_link(scrape_item.url)
        if self.is_attachment(scrape_item.url):
            return await self.handle_internal_link(scrape_item)
        if self.thread_url_part in scrape_item.url.parts:
            return await self.thread(scrape_item)
        if self.is_confirmation_link(scrape_item.url):
            url = await self.handle_confirmation_link(scrape_item.url)
            if url:  # If there was an error, this will be None
                # This could end up back in here if the URL goes to another thread
                scrape_item.url = url
                return self.handle_external_links(scrape_item)
        if any(p in scrape_item.url.parts for p in ("goto", "posts")):
            return await self.redirect(scrape_item)

        raise ValueError

    @error_handling_wrapper
    async def redirect(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            response, _ = await self.client._get_response_and_soup(self.domain, scrape_item.url)
        scrape_item.url = response.url
        self.manager.task_group.create_task(self.run(scrape_item))

    @error_handling_wrapper
    async def thread(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a forum thread."""
        scrape_item.set_type(FORUM, self.manager)
        thread = self.get_thread_info(scrape_item.url)
        title = None
        last_post_url = thread.url
        if thread.url in self.scraped_threads:
            return
        scrape_item.parent_threads.add(thread.url)
        self.scraped_threads.add(thread.url)
        async for soup in self.thread_pager(scrape_item):
            if not title:
                title_block = soup.select_one(self.selectors.title.element)
                try:
                    trash: list[Tag] = title_block.find_all(self.selectors.title_trash.element)  # type: ignore
                except AttributeError as e:
                    log_debug("Got an unprocessable soup", 40, exc_info=e)
                    raise ScrapeError(429, message="Invalid response from forum. You may have been rate limited") from e

                for element in trash:
                    element.decompose()

                title = self.create_title(title_block.text.replace("\n", ""), thread_id=thread.id_)  # type: ignore
                scrape_item.add_to_parent_title(title)

            posts = soup.select(self.selectors.posts.element)
            forum_thread_page = ForumThreadPage(thread, posts)
            continue_scraping, last_post_url = self.process_thread_page(scrape_item, forum_thread_page)
            if not continue_scraping:
                break

        await self.write_last_forum_post(thread.url, last_post_url)

    def process_thread_page(self, scrape_item: ScrapeItem, forum_page: ForumThreadPage) -> tuple[bool, URL]:
        continue_scraping = False
        thread = forum_page.thread
        post_url = thread.url
        for post in forum_page.posts:
            current_post = ForumPost(post, selectors=self.selectors.posts, post_name=self.POST_NAME)
            continue_scraping, scrape_post = self.check_post_number(thread.post, current_post.number)
            date = current_post.date
            post_string = f"{self.POST_NAME}{current_post.number}"
            post_url = thread.url / post_string
            if scrape_post:
                new_scrape_item = scrape_item.create_new(thread.url, possible_datetime=date, add_parent=post_url)
                self.manager.task_group.create_task(self.post(new_scrape_item, current_post))
                scrape_item.add_children()

            if not continue_scraping:
                break
        return continue_scraping, post_url

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, post: ForumPost) -> None:
        """Scrapes a post."""
        scrape_item.setup_as_post("")
        post_title = self.create_separate_post_title(None, str(post.number), post.date)
        scrape_item.add_to_parent_title(post_title)
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
        await self.process_children(scrape_item, embeds, selector.attribute, embeds=True)

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
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
            next_page = soup.select_one(self.selectors.next_page.element)
            yield soup
            if not next_page:
                break
            page_url_str: str = next_page.get(self.selectors.next_page.attribute)  # type: ignore
            page_url = self.parse_url(page_url_str)
            page_url = self.pre_filter_link(page_url)

    async def process_children(
        self, scrape_item: ScrapeItem, links: list[Tag], selector: str, *, embeds: bool = False
    ) -> None:
        for link_obj in links:
            link_tag: Tag | str | None = link_obj.get(selector)  # type: ignore
            if isinstance(link_tag, Tag):
                if link_tag.parent and (data_simp := link_tag.parent.get("data-simp")) and "init" in data_simp:
                    continue

                link_str: str | None = link_obj.get("href")  # type: ignore
            else:
                link_str = link_tag

            if not link_str:
                continue

            assert isinstance(link_str, str)
            if embeds:
                link_str = self.extract_embed_url(link_str)

            if not link_str or link_str.startswith("data:image/svg"):
                continue

            await self.process_child(scrape_item, link_str)

    @error_handling_wrapper
    async def process_child(self, scrape_item: ScrapeItem, link_str: str) -> None:
        link = await self.get_absolute_link(link_str)
        link = self.filter_link(link)
        if not link:
            return
        new_scrape_item = scrape_item.create_new(link)
        await self.handle_link(new_scrape_item)
        scrape_item.add_children()

    @singledispatchmethod
    def is_attachment(self, link: URL) -> bool:
        if not link:
            return False
        parts = self.attachment_url_parts
        hosts = self.attachment_url_hosts
        return any(p in link.parts for p in parts) or (link.host and any(h in link.host for h in hosts))  # type: ignore

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

    @error_handling_wrapper
    async def handle_link(self, scrape_item: ScrapeItem) -> None:
        if not scrape_item.url or scrape_item.url == self.primary_base_domain:
            return
        if not scrape_item.url.host:
            raise InvalidURLError("url has no host")
        if self.is_attachment(scrape_item.url):
            return await self.handle_internal_link(scrape_item)
        if self.primary_base_domain.host in scrape_item.url.host and self.stop_thread_recursion(scrape_item):  # type: ignore
            origin = scrape_item.parents[0]
            return log(f"Skipping nested thread URL {scrape_item.url} found on {origin}", 10)
        scrape_item.set_type(None, self.manager)
        self.handle_external_links(scrape_item)

    @error_handling_wrapper
    async def handle_internal_link(self, scrape_item: ScrapeItem) -> None:
        """Handles internal links."""
        scrape_item.url = remove_trailing_slash(scrape_item.url)

        if scrape_item.url.name.isdigit():
            head = await self.client.get_head(self.domain, scrape_item.url)  # type: ignore
            redirect = head.get("location")
            if not redirect:
                raise ScrapeError(422)
            scrape_item.url = self.parse_url(redirect)
            self.manager.task_group.create_task(self.run(scrape_item))
            return

        filename, ext = self.get_filename_and_ext(scrape_item.url.name, forum=True)
        scrape_item.add_to_parent_title("Attachments")
        scrape_item.part_of_album = True
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_confirmation_link(self, link: URL, *, origin: ScrapeItem | None = None) -> URL | None:
        """Handles link confirmation."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, link)
        confirm_button = soup.select_one("a[class*=button--cta]")
        if not confirm_button:
            return
        link_str: str = confirm_button.get("href")  # type: ignore
        link_str = link_str.split('" class="link link--internal', 1)[0]
        new_link = self.parse_url(link_str)
        return await self.get_absolute_link(new_link)

    def stop_thread_recursion(self, scrape_item: ScrapeItem) -> bool:
        max_thread_depth = self.manager.config_manager.settings_data.download_options.maximum_thread_depth
        if not max_thread_depth:
            return True
        if len(scrape_item.parent_threads) > max_thread_depth:
            return True
        return False

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
        link_str: str = link_obj.get(self.selectors.posts.links.element)  # type: ignore
        return not (is_image or self.is_attachment(link_str))

    def is_confirmation_link(self, link: URL) -> bool:
        return any(keyword in link.path for keyword in ("link-confirmation",))

    def extract_embed_url(self, embed_str: str) -> str | None:
        embed_str = embed_str.replace(r"\/\/", "https://www.").replace("\\", "")
        if match := re.search(HTTP_URL_REGEX, embed_str):
            return match.group(0).replace("www.", "")
        return embed_str

    def pre_filter_link(self, link: URL) -> URL:
        return link

    def filter_link(self, link: URL | None) -> URL | None:
        return link

    """ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def login_setup(self, login_url: URL) -> None:
        host_cookies: dict = self.client.client_manager.cookies.filter_cookies(self.primary_base_domain)
        session_cookie = host_cookies.get(self.session_cookie_name)
        session_cookie = session_cookie.value if session_cookie else None
        msg = f"No cookies found for {self.folder_domain}"
        if not session_cookie and self.login_required:
            raise LoginError(message=msg)

        _, self.logged_in = await self.check_login_with_request(login_url)

        if self.logged_in:
            return
        if session_cookie:
            msg = f"Cookies for {self.folder_domain} are not valid."
        if self.login_required:
            raise LoginError(message=msg)

        msg += " Scraping without an account"
        log(msg, 30)

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
                await asyncio.sleep(wait_time)
                data = prepare_login_data(text)
                _ = await self.client._post_data(self.domain, login_url / "login", data=data, cache_disabled=True)
                await asyncio.sleep(wait_time)
                text, logged_in = await self.check_login_with_request(login_url)
                if logged_in:
                    self.logged_in = True
                    return

        msg = f"Failed to login on {self.folder_domain} after {retries} attempts"
        raise LoginError(message=msg)

    async def check_login_with_request(self, login_url: URL) -> tuple[str, bool]:
        text = await self.client.get_text(self.domain, login_url, cache_disabled=True)
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
