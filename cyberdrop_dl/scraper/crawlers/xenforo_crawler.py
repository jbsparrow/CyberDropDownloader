from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FORUM, FORUM_POST, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup, Tag

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
    soup: BeautifulSoup
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
    POST_NAME = None
    thread_url_part = "threads"

    def __init__(self, manager: Manager, site: str, folder_domain: str | None = None) -> None:
        super().__init__(manager, site, folder_domain)
        self.primary_base_domain = self.primary_base_domain or URL(f"https://{site}")
        self.POST_NAME = self.POST_NAME | "post-"
        self.attachment_url_part = ["attachments"]
        self.attachment_url_hosts = ["smgmedia", "attachments.f95zone"]
        self.logged_in = False
        self.login_attempts = 0
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def pre_filter_link(self, link: URL) -> URL:
        return link

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        scrape_item.url = await self.pre_filter_link(scrape_item.url)
        if self.thread_url_part not in scrape_item.url.parts:
            log(f"Scrape Failed: Unknown URL path: {scrape_item.url}", 40)
            return

        if not self.logged_in and self.login_attempts == 0:
            await self.try_login()

        await self.thread(scrape_item)

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
            self.login_attempts += 1
            await self.forum_login(login_url, session_cookie, username, password)

        if not self.logged_in:
            msg = f"{self.folder_domain} login failed. "
            if not self.login_required:
                msg += "Scraping without an account."
            log(msg, 40)

    @error_handling_wrapper
    async def thread(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a forum thread."""
        if not self.logged_in and self.login_required:
            return

        scrape_item.set_type(FORUM, self.manager)

        thread_url = scrape_item.url
        post_number = 0
        post_sections = {scrape_item.url.fragment}
        threads_part_index = scrape_item.url.parts.index(self.thread_url_part)
        thread_id = thread_url.parts[threads_part_index].split(".")[-1].split("#")[0]
        post_part_index = threads_part_index + 1
        if len(scrape_item.url.parts) > post_part_index:
            post_sections.add(scrape_item.url.parts[post_part_index])

        if any(self.POST_NAME in sec for sec in post_sections):
            url_parts = str(scrape_item.url).rsplit(self.POST_NAME, 1)
            thread_url = URL(url_parts[0].rstrip("#"))
            post_number = int(url_parts[-1].strip("/")) if len(url_parts) == 2 else 0

        last_scraped_post_number = None
        async for soup in self.thread_pager(scrape_item):
            title_block = soup.select_one(self.selectors.title.element)
            trash: list[Tag] = title_block.find_all(self.selectors.title_trash.element)
            for element in trash:
                element.decompose()

            title = self.create_title(title_block.text.replace("\n", ""), thread_id=thread_id)
            posts = soup.select(self.selectors.posts.element)
            continue_scraping = False
            for post in posts:
                current_post = ForumPost(post, selectors=self.selectors.posts, post_name=self.POST_NAME)
                last_scraped_post_number = current_post.number
                scrape_post, continue_scraping = self.check_post_number(post_number, current_post.number)

                if scrape_post:
                    new_scrape_item = self.create_scrape_item(
                        scrape_item,
                        thread_url,
                        title,
                        possible_datetime=current_post.date,
                        add_parent=scrape_item.url.joinpath(f"{self.POST_NAME}{current_post.number}"),
                    )
                    trash: list[Tag] = title_block.find_all(self.selectors.quotes.element)
                    for element in trash:
                        element.decompose()

                    await self.post(new_scrape_item, current_post)
                    scrape_item.add_children()

                if not continue_scraping:
                    break
            if not continue_scraping:
                break

        await self.write_last_forum_post(scrape_item, last_scraped_post_number)

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

    def process_embed(self, data: str) -> URL:
        if not data:
            return
        data = data.replace(r"\/\/", "https://www.").replace("\\", "")
        embed = re.search(HTTP_URL_PATTERNS[0], data) or re.search(HTTP_URL_PATTERNS[1], data)
        return embed.group(0).replace("www.", "") if embed else data

    async def filter_link(self, link: URL) -> URL:
        return link

    async def process_children(self, scrape_item: ScrapeItem, links: list[Tag], selector: str) -> None:
        for link_obj in links:
            link: Tag = link_obj.get(selector) or link_obj.get("href")
            if not link:
                continue
            if not isinstance(link, str):
                parent_simp_check = link.parent.get("data-simp")
                if parent_simp_check and "init" in parent_simp_check:
                    continue
            if selector == self.selectors.posts.embeds.attribute:
                link = self.process_embed(link)
            if not link:
                continue
            if str(link).startswith("data:image/svg"):
                continue
            link = await self.get_absolute_link(link)
            link = await self.filter_link(link)
            if not link:
                continue
            await self.handle_link(scrape_item, link)
            scrape_item.add_children()

    def is_attachment(self, link: URL | str) -> bool:
        if not link:
            return False
        if isinstance(link, str):
            link = URL(link)
        return any(part in link.parts for part in self.attachment_url_part) or any(
            host in link.host for host in self.attachment_url_hosts
        )

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

    async def is_confirmation_link(self, link: URL) -> bool:
        return False

    @error_handling_wrapper
    async def handle_confirmation_link(self, link: URL, *, origin: ScrapeItem | None = None) -> URL | None:
        """Handles link confirmation."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, link, origin=origin)
        confirm_button = soup.select_one("a[class*=button--cta]")
        if confirm_button:
            return URL(confirm_button.get("href"))
        return None

    async def write_last_forum_post(self, scrape_item: ScrapeItem, post_number: int) -> None:
        if not post_number:
            return
        post_string = f"{self.POST_NAME}{post_number}"
        if "page-" in scrape_item.url.raw_name or self.POST_NAME in scrape_item.url.raw_name:
            last_post_url = scrape_item.url.parent / post_string
        else:
            last_post_url = scrape_item.url / post_string
        await self.manager.log_manager.write_last_post_log(last_post_url)

    async def thread_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of forum thread pages."""
        page_url = scrape_item.url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select_one(self.selectors.next_page.element)
            yield soup
            if next_page:
                page_url = next_page.get(self.selectors.next_page.attribute)
                if page_url:
                    if page_url.startswith("/"):
                        page_url = self.primary_base_domain / page_url[1:]
                    page_url = URL(page_url)
                    page_url = await self.pre_filter_link(page_url)
                    continue
            break

    def is_valid_post_link(self, link_obj: Tag) -> bool:
        is_image = link_obj.select_one("img")
        link = link_obj.get(self.selectors.posts.links.element)
        return not (is_image and self.is_attachment(link))

    async def get_absolute_link(self, link: URL | str) -> URL:
        if isinstance(link, str):
            encoded = "%" in link
            link = link.replace(".th.", ".").replace(".md.", ".").replace("ifr", "watch")
            if link.endswith("/"):
                link = link[:-1]
            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = self.primary_base_domain.joinpath(link[1:], encoded=encoded)

        if isinstance(link, str):
            link = URL(link, encoded=encoded)
        if await self.is_confirmation_link(link) or any(keyword in link.path for keyword in ("link-confirmation",)):
            link = await self.handle_confirmation_link(link)

        return link
