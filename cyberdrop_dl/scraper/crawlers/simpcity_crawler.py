from __future__ import annotations

import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import Tag, BeautifulSoup
from yarl import URL
import json

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper, log

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class SimpCityCrawler(Crawler):
    def __init__(self, manager: Manager):
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
        self.label_selector = "a[class=label]"
        self.tag_selector = "a[class=tagItem]"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)

        if not self.logged_in and self.login_attempts == 0:
            login_url = self.primary_base_domain / "login"
            username = self.manager.config_manager.authentication_data['Forums']['simpcity_username']
            password = self.manager.config_manager.authentication_data['Forums']['simpcity_password']
            wait_time = 5
            
            try:
                ddg1 = self.manager.config_manager.authentication_data['Forums']['simpcity_ddg_cookie_1']
                ddg2 = self.manager.config_manager.authentication_data['Forums']['simpcity_ddg_cookie_2']
                ddg5 = self.manager.config_manager.authentication_data['Forums']['simpcity_ddg_cookie_5']
                ddg_id = self.manager.config_manager.authentication_data['Forums']['simpcity_ddg_id']
                ddg_mark = self.manager.config_manager.authentication_data['Forums']['simpcity_ddg_mark']
                self.manager.client_manager.cookies.update_cookies({"__ddg1_": ddg1, "__ddg2_": ddg2, "__ddg5_": ddg5, "__ddgid_": ddg_id, "__ddgmark_": ddg_mark}, response_url=URL("https://" + login_url.host))
            except KeyError:
                await log("SimpCity DDOS-Guard cookies not found. Skipping SimpCity.", 40)
                return

            if username and password:
                self.login_attempts += 1
                await self.forum_login(login_url, None, username, password, wait_time)

        if not self.logged_in and self.login_attempts == 1:
            await log("SimpCity login failed. Scraping without an account.", 40)

        await self.forum(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def forum(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        continue_scraping = True

        thread_url = scrape_item.url
        post_number = 0
        if len(scrape_item.url.parts) > 3:
            if "post-" in str(scrape_item.url.parts[3]) or "post-" in scrape_item.url.fragment:
                url_parts = str(scrape_item.url).rsplit("post-", 1)
                thread_url = URL(url_parts[0].rstrip("#"))
                post_number = int(url_parts[-1].strip("/")) if len(url_parts) == 2 else 0

        current_post_number = 0
        while True:
            posts_dict= self.manager.simpcity_cache_manager.get(str(thread_url))
            if not posts_dict:
                async with self.request_limiter:
                    soup = await self.client.get_BS4(self.domain, thread_url)
                title_block = soup.select_one(self.title_selector)
                for elem in title_block.find_all(self.title_trash_selector):
                    elem.decompose()
                thread_id = thread_url.parts[2].split('.')[-1]
                title = await self.create_title(title_block.text.replace("\n", ""), None, thread_id)
                posts = soup.select(self.posts_selector)
                post_content_array=[]
                for post in posts:
                    current_post_number = int(
                        post.select_one(self.posts_number_selector).get(self.posts_number_attribute).split('/')[-1].split(
                            'post-')[-1])
                    scrape_post, continue_scraping = await self.check_post_number(post_number, current_post_number)

                    if scrape_post:
                        try:
                            date = int(post.select_one(self.post_date_selector).get(self.post_date_attribute))
                        except:
                            pass
                        new_scrape_item = await self.create_scrape_item(scrape_item, thread_url, title, False, None, date)

                        # for elem in post.find_all(self.quotes_selector):
                        #     elem.decompose()
                        post_content = post.select_one(self.posts_content_selector)
                        post_content_array.append({"data"   : str(post_content),"current_post_number":current_post_number})

                        await self.post(new_scrape_item, post_content, current_post_number)
                    simp_dict={"posts": post_content_array,"title": title,"date":date}
                    self.manager.simpcity_cache_manager.save(str(thread_url),json.dumps(simp_dict))
                    if not continue_scraping:
                        break
            else:
                posts_dict=json.loads(posts_dict)
                title =posts_dict.get("title")
                posts= posts_dict.get("posts")
                date = posts_dict.get("date")

                for post in posts:
                    current_post_number = post.get("current_post_number")
                    scrape_post, continue_scraping = await self.check_post_number(post_number, current_post_number)

                    if scrape_post:
                        new_scrape_item = await self.create_scrape_item(scrape_item, thread_url, title, False, None, date)

                        # for elem in post.find_all(self.quotes_selector):
                        #     elem.decompose()
                        post_content =BeautifulSoup(post.get("data"))
    
                        await self.post(new_scrape_item, post_content, current_post_number)
                    if not continue_scraping:
                        break


            post_string = f"post-{current_post_number}"
            if "page-" in scrape_item.url.raw_name or "post-" in scrape_item.url.raw_name:
                last_post_url = scrape_item.url.parent / post_string
            else:
                last_post_url = scrape_item.url / post_string
            await self.manager.log_manager.write_last_post_log(last_post_url)

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, post_content: Tag, post_number: int) -> None:
        """Scrapes a post"""
        if self.manager.config_manager.settings_data['Download_Options']['separate_posts']:
            scrape_item = await self.create_scrape_item(scrape_item, scrape_item.url, "")
            await scrape_item.add_to_parent_title("post-" + str(post_number))

        await self.links(scrape_item, post_content)
        await self.images(scrape_item, post_content)
        await self.videos(scrape_item, post_content)
        await self.embeds(scrape_item, post_content)
        await self.attachments(scrape_item, post_content)

    @error_handling_wrapper
    async def links(self, scrape_item: ScrapeItem, post_content: Tag) -> None:
        """Scrapes links from a post"""
        links = post_content.select(self.links_selector)
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
                    new_scrape_item = await self.create_scrape_item(scrape_item, link, "")
                    await self.handle_external_links(new_scrape_item)
                elif self.attachment_url_part in link.parts:
                    await self.handle_internal_links(link, scrape_item)
                else:
                    await log(f"Unknown link type: {link}", 30)
                    continue
            except TypeError:
                await log(f"Scrape Failed: encountered while handling {link}", 40)

    @error_handling_wrapper
    async def images(self, scrape_item: ScrapeItem, post_content: Tag) -> None:
        """Scrapes images from a post"""
        images = post_content.select(self.images_selector)
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
                new_scrape_item = await self.create_scrape_item(scrape_item, link, "")
                await self.handle_external_links(new_scrape_item)
            elif self.attachment_url_part in link.parts:
                continue
            else:
                await log(f"Unknown image type: {link}", 30)
                continue

    @error_handling_wrapper
    async def videos(self, scrape_item: ScrapeItem, post_content: Tag) -> None:
        """Scrapes videos from a post"""
        videos = post_content.select(self.videos_selector)
        videos.extend(post_content.select(self.iframe_selector))

        for video in videos:
            link = video.get(self.videos_attribute)
            if not link:
                continue

            if link.endswith("/"):
                link = link[:-1]

            if link.startswith("//"):
                link = "https:" + link

            link = URL(link)
            new_scrape_item = await self.create_scrape_item(scrape_item, link, "")
            await self.handle_external_links(new_scrape_item)

    @error_handling_wrapper
    async def embeds(self, scrape_item: ScrapeItem, post_content: Tag) -> None:
        """Scrapes embeds from a post"""
        embeds = post_content.select(self.embeds_selector)
        for embed in embeds:
            data = embed.get(self.embeds_attribute)
            if not data:
                continue

            data = data.replace("\/\/", "https://www.")
            data = data.replace("\\", "")

            embed = re.search(
                r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}\\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)", data)
            if not embed:
                embed = re.search(
                    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,4}\/[-a-zA-Z0-9@:%._\+~#=]*\/[-a-zA-Z0-9@:?&%._\+~#=]*",
                    data)

            if embed:
                link = embed.group(0).replace("www.", "")
                if link.endswith("/"):
                    link = link[:-1]
                link = URL(link)
                new_scrape_item = await self.create_scrape_item(scrape_item, link, "")
                await self.handle_external_links(new_scrape_item)

    @error_handling_wrapper
    async def attachments(self, scrape_item: ScrapeItem, post_content: Tag) -> None:
        """Scrapes attachments from a post"""
        attachment_block = post_content.select_one(self.attachments_block_selector)
        if not attachment_block:
            return

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
                new_scrape_item = await self.create_scrape_item(scrape_item, link, "")
                await self.handle_external_links(new_scrape_item)
            elif self.attachment_url_part in link.parts:
                await self.handle_internal_links(link, scrape_item)
            else:
                await log(f"Unknown image type: {link}", 30)
                continue

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def handle_internal_links(self, link: URL, scrape_item: ScrapeItem) -> None:
        """Handles internal links"""
        filename, ext = await get_filename_and_ext(link.name, True)
        new_scrape_item = await self.create_scrape_item(scrape_item, link, "Attachments", True)
        await self.handle_file(link, new_scrape_item, filename, ext)
