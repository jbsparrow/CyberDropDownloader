from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FORUM, FORUM_POST, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager


class SimpCityCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "simpcity", "SimpCity")
        self.primary_base_domain = URL("https://simpcity.su")
        self.logged_in = False
        self.login_attempts = 0
        self.request_limiter = AsyncLimiter(10, 1)

        self.title_selector = "h1[class=p-title-value]"
        self.title_trash_selector = "span"
        self.posts_selector = "div[class*=message-main]"
        self.post_date_selector = "time"
        self.post_date_attribute = "data-timestamp"
        self.posts_number_selector = "li[class=u-concealed] a"
        self.posts_number_attribute = "href"
        self.quotes_selector = "blockquote"
        self.posts_content_selector = "div[class*=message-userContent]"
        self.next_page_selector = "a[class*=pageNav-jump--next]"
        self.next_page_attribute = "href"
        self.links_selector = "a"
        self.links_attribute = "href"
        self.attachment_url_part = "attachments"
        self.images_selector = "img[class*=bbImage]"
        self.images_attribute = "src"
        self.videos_selector = "video source"
        self.iframe_selector = "iframe[class=saint-iframe]"
        self.videos_attribute = "src"
        self.embeds_selector = "span[data-s9e-mediaembed-iframe]"
        self.embeds_attribute = "data-s9e-mediaembed-iframe"
        self.attachments_block_selector = "section[class=message-attachments]"
        self.attachments_selector = "a"
        self.attachments_attribute = "href"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if not self.logged_in and self.login_attempts == 0:
            login_url = self.primary_base_domain / "login"
            host_cookies = self.client.client_manager.cookies._cookies.get((self.primary_base_domain.host, ""), {})
            session_cookie = host_cookies.get("xf_user").value if "xf_user" in host_cookies else None
            if not session_cookie:
                session_cookie = self.manager.config_manager.authentication_data["Forums"].get(
                    "simpcity_xf_user_cookie"
                )

            session_cookie = self.manager.config_manager.authentication_data["Forums"]["simpcity_xf_user_cookie"]
            username = self.manager.config_manager.authentication_data["Forums"]["simpcity_username"]
            password = self.manager.config_manager.authentication_data["Forums"]["simpcity_password"]
            wait_time = 5

            if session_cookie or (username and password):
                self.login_attempts += 1
                await self.forum_login(login_url, session_cookie, username, password, wait_time)

        if not self.logged_in and self.login_attempts == 1:
            log("SimpCity login failed. Scraping without an account.", 40)

        await self.forum(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def forum(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        continue_scraping = True

        thread_url = scrape_item.url
        post_number = 0
        scrape_item.type = FORUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]
        post_sections = (scrape_item.url.parts[3], scrape_item.url.fragment)
        if len(scrape_item.url.parts) > 3 and any("post-" in sec for sec in post_sections):
            url_parts = str(scrape_item.url).rsplit("post-", 1)
            thread_url = URL(url_parts[0].rstrip("#"))
            post_number = int(url_parts[-1].strip("/")) if len(url_parts) == 2 else 0

        current_post_number = 0
        while True:
            thread_url = scrape_item.url if current_post_number == 0 else thread_url
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, thread_url, origin=scrape_item)

            title_block = soup.select_one(self.title_selector)
            for elem in title_block.find_all(self.title_trash_selector):
                elem.decompose()

            thread_id = thread_url.parts[2].split(".")[-1]
            title = self.create_title(title_block.text.replace("\n", ""), None, thread_id)

            posts = soup.select(self.posts_selector)
            for post in posts:
                current_post_number = int(
                    post.select_one(self.posts_number_selector)
                    .get(self.posts_number_attribute)
                    .split("/")[-1]
                    .split("post-")[-1],
                )
                scrape_post, continue_scraping = self.check_post_number(post_number, current_post_number)

                if scrape_post:
                    date = None
                    with contextlib.suppress(AttributeError):
                        date = int(post.select_one(self.post_date_selector).get(self.post_date_attribute))
                    new_scrape_item = self.create_scrape_item(
                        scrape_item,
                        thread_url,
                        title,
                        False,
                        None,
                        date,
                        add_parent=scrape_item.url.joinpath(f"post-{current_post_number}"),
                    )

                    # for elem in post.find_all(self.quotes_selector):
                    #     elem.decompose()
                    post_content = post.select_one(self.posts_content_selector)
                    await self.post(new_scrape_item, post_content, current_post_number)

                    scrape_item.children += 1
                    if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                        raise MaxChildrenError(origin=scrape_item)

                if not continue_scraping:
                    break

            next_page = soup.select_one(self.next_page_selector)
            if next_page and continue_scraping:
                thread_url = next_page.get(self.next_page_attribute)
                if thread_url:
                    if thread_url.startswith("/"):
                        thread_url = self.primary_base_domain / thread_url[1:]
                    thread_url = URL(thread_url)
                    continue
            else:
                break
        post_string = f"post-{current_post_number}"
        if "page-" in scrape_item.url.raw_name or "post-" in scrape_item.url.raw_name:
            last_post_url = scrape_item.url.parent / post_string
        else:
            last_post_url = scrape_item.url / post_string
        await self.manager.log_manager.write_last_post_log(last_post_url)

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, post_content: Tag, post_number: int) -> None:
        """Scrapes a post."""
        if self.manager.config_manager.settings_data["Download_Options"]["separate_posts"]:
            scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, "")
            scrape_item.add_to_parent_title("post-" + str(post_number))

        scrape_item.type = FORUM_POST
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        posts_scrapers = [self.links, self.images, self.videos, self.embeds, self.attachments]

        for scraper in posts_scrapers:
            scrape_item.children += await scraper(scrape_item, post_content)
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def links(self, scrape_item: ScrapeItem, post_content: Tag) -> int:
        """Scrapes links from a post."""
        links = post_content.select(self.links_selector)
        new_children = 0
        for link_obj in links:
            test_for_img = link_obj.select_one("img")
            if test_for_img is not None and self.attachment_url_part not in link_obj.get(self.links_attribute):
                continue

            link = link_obj.get(self.links_attribute)
            if not link:
                continue

            link = link.replace(".th.", ".").replace(".md.", ".")

            if link.endswith("/"):
                link = link[:-1]

            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = self.primary_base_domain / link[1:]
            link = URL(link)

            try:
                if self.domain not in link.host:
                    new_scrape_item = self.create_scrape_item(scrape_item, link, "")
                    self.handle_external_links(new_scrape_item)
                elif self.attachment_url_part in link.parts:
                    await self.handle_internal_links(link, scrape_item)
                else:
                    log(f"Unknown link type: {link}", 30)
            except TypeError:
                log(f"Scrape Failed: encountered while handling {link}", 40)
            new_children += 1
            if scrape_item.children_limit and (new_children + scrape_item.children) >= scrape_item.children_limit:
                break
        return new_children

    @error_handling_wrapper
    async def images(self, scrape_item: ScrapeItem, post_content: Tag) -> int:
        """Scrapes images from a post."""
        images = post_content.select(self.images_selector)
        new_children = 0
        for image in images:
            link = image.get(self.images_attribute)
            if not link:
                continue

            parent_simp_check = image.parent.get("data-simp")
            if parent_simp_check and "init" in parent_simp_check:
                continue

            link = link.replace(".th.", ".").replace(".md.", ".")
            if link.endswith("/"):
                link = link[:-1]

            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = self.primary_base_domain / link[1:]
            link = URL(link)

            if self.domain not in link.host:
                new_scrape_item = self.create_scrape_item(scrape_item, link, "")
                self.handle_external_links(new_scrape_item)
            elif self.attachment_url_part in link.parts:
                continue
            else:
                log(f"Unknown image type: {link}", 30)
            new_children += 1
            if scrape_item.children_limit and (new_children + scrape_item.children) >= scrape_item.children_limit:
                break
        return new_children

    @error_handling_wrapper
    async def videos(self, scrape_item: ScrapeItem, post_content: Tag) -> int:
        """Scrapes videos from a post."""
        videos = post_content.select(self.videos_selector)
        videos.extend(post_content.select(self.iframe_selector))
        new_children = 0
        for video in videos:
            link = video.get(self.videos_attribute)
            if not link:
                continue

            if link.endswith("/"):
                link = link[:-1]

            if link.startswith("//"):
                link = "https:" + link

            link = URL(link)
            new_scrape_item = self.create_scrape_item(scrape_item, link, "")
            self.handle_external_links(new_scrape_item)
            new_children += 1
            if scrape_item.children_limit and (new_children + scrape_item.children) >= scrape_item.children_limit:
                break
        return new_children

    @error_handling_wrapper
    async def embeds(self, scrape_item: ScrapeItem, post_content: Tag) -> int:
        """Scrapes embeds from a post."""
        embeds = post_content.select(self.embeds_selector)
        new_children = 0
        for embed in embeds:
            data = embed.get(self.embeds_attribute)
            if not data:
                continue

            data = data.replace(r"\/\/", "https://www.")
            data = data.replace("\\", "")

            embed = re.search(
                r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}\\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)",
                data,
            )
            if not embed:
                embed = re.search(
                    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}\/[-a-zA-Z0-9@:%._\+~#=]*\/[-a-zA-Z0-9@:?&%._\+~#=]*",
                    data,
                )

            if embed:
                link = embed.group(0).replace("www.", "")
                if link.endswith("/"):
                    link = link[:-1]
                link = URL(link)
                new_scrape_item = self.create_scrape_item(scrape_item, link, "")
                self.handle_external_links(new_scrape_item)
                new_children += 1
                if scrape_item.children_limit and (new_children + scrape_item.children) >= scrape_item.children_limit:
                    break
        return new_children

    @error_handling_wrapper
    async def attachments(self, scrape_item: ScrapeItem, post_content: Tag) -> int:
        """Scrapes attachments from a post."""
        attachment_block = post_content.select_one(self.attachments_block_selector)
        new_children = 0
        if not attachment_block:
            return new_children
        attachments = attachment_block.select(self.attachments_selector)
        for attachment in attachments:
            link = attachment.get(self.attachments_attribute)
            if not link:
                continue

            if link.endswith("/"):
                link = link[:-1]

            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = self.primary_base_domain / link[1:]
            link = URL(link)

            if self.domain not in link.host:
                new_scrape_item = self.create_scrape_item(scrape_item, link, "")
                self.handle_external_links(new_scrape_item)
            elif self.attachment_url_part in link.parts:
                await self.handle_internal_links(link, scrape_item)
            else:
                log(f"Unknown image type: {link}", 30)
            new_children += 1
            if scrape_item.children_limit and (new_children + scrape_item.children) >= scrape_item.children_limit:
                break
        return new_children

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def handle_internal_links(self, link: URL, scrape_item: ScrapeItem) -> None:
        """Handles internal links."""
        filename, ext = get_filename_and_ext(link.name, True)
        new_scrape_item = self.create_scrape_item(scrape_item, link, "Attachments", True)
        await self.handle_file(link, new_scrape_item, filename, ext)
