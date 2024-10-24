from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from aiolimiter import AsyncLimiter
from yarl import URL
from multidict import MultiDict
from datetime import datetime, timedelta
import re
from calendar import timegm

from cyberdrop_dl.clients.errors import ScrapeFailure
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import get_filename_and_ext, error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from bs4 import BeautifulSoup

DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)

class TokioMotionCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "tokyomotion", "Tokyomotion")
        self.primary_base_domain = URL("https://www.tokyomotion.net")
        self.request_limiter = AsyncLimiter(10, 1)

        self.album_selector = 'a[href^="/album/"]'
        self.image_div_selector = "div[id*='_photo_']"
        self.image_selector = 'a[href^="/photo/"]'
        self.image_thumb_selector = "img[id^='album_photo_']"
        self.next_page_attribute = "href"
        self.next_page_selector = 'a.prevnext'
        self.title_selector = "meta[property='og:title']"
        self.video_div_selector = "div[id*='video_']"
        self.video_selector = 'a[href^="/video/"]'
        self.search_div_selector = "div[class^='well']"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)
        new_query = MultiDict(scrape_item.url.query)
        new_query.pop('page', None)  
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path).with_query(new_query)

        if 'video' in scrape_item.url.parts:
            await self.video(scrape_item)

        elif 'videos' in scrape_item.url.parts:
            await self.playlist(scrape_item)

        elif 'photo' in scrape_item.url.parts:
            await self.image(scrape_item)

        elif any(part in scrape_item.url.parts for part in ('album','photos')):
            await self.album(scrape_item)

        elif 'albums' in scrape_item.url.parts:
            await self.albums(scrape_item)

        elif 'user' in scrape_item.url.parts:
            await self.profile(scrape_item)

        else:
            await self.search(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video"""
        if await self.check_complete_from_referer(scrape_item):
            return
        
        video_id = scrape_item.url.parts[2]
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url)

        try:
            relative_date_str = soup.select_one("div.pull-right.big-views-xs.visible-xs > span.text-white").text.strip()
            date = await self.parse_relative_date(relative_date_str)
            scrape_item.possible_datetime = date
        except AttributeError:
            pass
            
        try:
            srcSD = soup.select_one('source[title="SD"]')
            srcHD = soup.select_one('source[title="HD"]')
            src = (srcHD or srcSD).get('src')
            link = URL(src)
        except AttributeError:
            if "This is a private" in soup.text:
                raise ScrapeFailure(403, f"Private video: {scrape_item.url}")
            raise ScrapeFailure(404, f"Could not find video source for {scrape_item.url}")
        
        title = soup.select_one('title').text.rsplit(" - TOKYO Motion")[0].strip()
       
        # NOTE: hardcoding the extension to prevent quering the final server URL
        # final server URL is always diferent so it can not be saved to db.
        filename, ext = f"{video_id}.mp4", '.mp4'
        custom_file_name, _ = await get_filename_and_ext(f"{title} [{video_id}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_file_name)

    @error_handling_wrapper
    async def albums(self, scrape_item: ScrapeItem) -> None:
        """Scrapes user albums"""
        user = scrape_item.url.parts[2]
        user_title = await self.create_title(f"{user} [user]", scrape_item.album_id, None)
        if user_title not in scrape_item.parent_title.split('/'):
            await scrape_item.add_to_parent_title(user_title)

        async for soup in self.web_pager(scrape_item.url):
            albums = soup.select(self.album_selector)
            for album in albums:
                link = album.get('href')
                if not link:
                    continue

                if link.startswith("/"):
                    link = self.primary_base_domain / link[1:]

                link = URL(link)
                new_scrape_item = await self.create_scrape_item(scrape_item, link, "albums", add_parent = scrape_item.url)
                await self.album(new_scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        title = scrape_item.url.parts[-1]
        if 'user' in scrape_item.url.parts:
            user = scrape_item.url.parts[2]
            user_title = await self.create_title(f"{user} [user]", scrape_item.album_id, None)
            if user_title not in scrape_item.parent_title.split('/'):
                await scrape_item.add_to_parent_title(user_title)

        else:
            scrape_item.album_id = scrape_item.url.parts[2]
            scrape_item.part_of_album=True
        
        if self.folder_domain not in scrape_item.parent_title:
            title = await self.create_title(title, scrape_item.album_id, None)

        if 'favorite' in scrape_item.url.parts:
            await scrape_item.add_to_parent_title('favorite')

        if title not in scrape_item.parent_title.split('/'):
            await scrape_item.add_to_parent_title(title)

        async for soup in self.web_pager(scrape_item.url):
            if "This is a private" in soup.text:
                raise ScrapeFailure(403, f"Private album: {scrape_item.url}")
            images = soup.select(self.image_div_selector)
            for image in images:
                link = image.select_one(self.image_thumb_selector)
                if not link:
                    continue

                link = link.get('src')
                if link.startswith("/"):
                    link = self.primary_base_domain / link[1:]

                link = URL(link)
                link=link.with_path(link.path.replace("/tmb/", "/"))

                filename, ext = await get_filename_and_ext(link.name)
                await self.handle_file(link, scrape_item, filename, ext)
    
    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image"""
        if await self.check_complete_from_referer(scrape_item):
            return
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url)
        try:
            img = soup.select_one("img[class='img-responsive-mw']")
            src = img.get('src')
            link = URL(src)
        except AttributeError:
            if "This is a private" in soup.text:
                raise ScrapeFailure(403, f"Private Photo: {scrape_item.url}")
            raise ScrapeFailure(404, f"Could not find image source for {scrape_item.url}")
        
        filename, ext = await get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
    
    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user profile"""
        user = scrape_item.url.parts[2]
        user_title = await self.create_title(f"{user} [user]", scrape_item.album_id, None)
        if user_title not in scrape_item.parent_title.split('/'):
            await scrape_item.add_to_parent_title(user_title)

        new_parts = ['albums','favorite/photos', 'videos','favorite/videos']
        scrapers = [ self.albums, self.album, self.playlist, self.playlist]
        for part, scraper in zip(new_parts, scrapers):
            link = scrape_item.url / part
            new_scrape_item = await self.create_scrape_item(scrape_item, link, "", add_parent = scrape_item.url)
            await scraper(new_scrape_item)
    
    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a search result"""
        search_type = scrape_item.url.query.get('search_type')
        if 'search' not in scrape_item.url.parts or search_type == 'users':
            return 
        
        search_query = scrape_item.url.query.get('search_query')
        search_title = await self.create_title(f"{search_query} [{search_type} search]", scrape_item.album_id, None)
        if search_title not in scrape_item.parent_title.split('/'):
            await scrape_item.add_to_parent_title(search_title)

        selector = self.video_selector
        scraper = self.video
        
        if search_type=='photos':
            selector = self.album_selector
            scraper = self.album

        async for soup in self.web_pager(scrape_item.url):
            results = soup.select(self.search_div_selector)
            for result in results:
                link = result.select_one(selector)
                if not link:
                    continue

                link = link.get('href')
                if link.startswith("/"):
                    link = self.primary_base_domain / link[1:]

                link = URL(link)
                new_scrape_item = await self.create_scrape_item(scrape_item, link, "", add_parent = scrape_item.url)
                await scraper(new_scrape_item)
    
    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video playlist"""
        title = scrape_item.url.parts[-1]
        user = scrape_item.url.parts[2]
        user_title = await self.create_title(f"{user} [user]", scrape_item.album_id, None)
        if user_title not in scrape_item.parent_title.split('/'):
            await scrape_item.add_to_parent_title(user_title)

        if 'favorite' in scrape_item.url.parts:
            await scrape_item.add_to_parent_title('favorite')

        if self.folder_domain not in scrape_item.parent_title:
            title = await self.create_title(title, scrape_item.album_id, None)

        if title not in scrape_item.parent_title.split('/'):
            await scrape_item.add_to_parent_title(title)

        async for soup in self.web_pager(scrape_item.url):
            if "This is a private" in soup.text:
                raise ScrapeFailure(403, f"Private playlist: {scrape_item.url}")
            videos = soup.select(self.video_div_selector)
            for video in videos:
                link = video.select_one(self.video_selector)
                if not link:
                    continue

                link = link.get('href')
                if link.startswith("/"):
                    link = self.primary_base_domain / link[1:]

                link = URL(link)
                new_scrape_item = await self.create_scrape_item(scrape_item, link, "", add_parent = scrape_item.url)
                await self.video(new_scrape_item)

    async def web_pager(self, url: URL) -> AsyncGenerator[BeautifulSoup]:
        "Generator of website pages"
        page_url = url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_BS4(self.domain, page_url)
            next_page = soup.select_one(self.next_page_selector)
            yield soup
            if next_page :
                page_url = next_page.get(self.next_page_attribute)
                if page_url:
                    if page_url.startswith("/"):
                        page_url = self.primary_base_domain / page_url[1:]
                    page_url = URL(page_url)
                    continue
            break

    async def parse_relative_date(self, relative_date: timedelta|str) -> int:
        """Parses `datetime.timedelta` or `string` in a timedelta format. Returns `now() - parsed_timedelta` as an unix timestamp"""
        if isinstance(relative_date,str):
            time_str = relative_date.casefold()
            matches: list[str] = re.findall(DATE_PATTERN, time_str)

            # Assume today
            time_dict = {'days':0}

            for value, unit in matches:
                value = int(value)
                unit = unit.lower()
                time_dict[unit] = value

            relative_date = timedelta (**time_dict)

        date = datetime.now() - relative_date
        return timegm(date.timetuple())
