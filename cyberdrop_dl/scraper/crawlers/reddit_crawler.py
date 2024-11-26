from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, ClassVar

import aiohttp
import asyncpraw
import asyncprawcore
from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError, NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from asyncpraw.models import Redditor, Submission, Subreddit

    from cyberdrop_dl.managers.manager import Manager


class RedditCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"reddit": ["reddit", "redd.it"]}

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, "Reddit")
        self.reddit_personal_use_script = self.manager.config_manager.authentication_data.reddit.personal_use_script
        self.reddit_secret = self.manager.config_manager.authentication_data.reddit.secret
        self.request_limiter = AsyncLimiter(5, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if not self.reddit_personal_use_script or not self.reddit_secret:
            log("Reddit API credentials not found. Skipping.", 30)
            self.manager.progress_manager.scrape_stats_progress.add_failure("Failed Login")
            self.scraping_progress.remove_task(task_id)
            return

        async with aiohttp.ClientSession() as reddit_session:
            reddit = asyncpraw.Reddit(
                client_id=self.reddit_personal_use_script,
                client_secret=self.reddit_secret,
                user_agent="CyberDrop-DL",
                requestor_kwargs={"session": reddit_session},
                check_for_updates=False,
            )

            if "user" in scrape_item.url.parts or "u" in scrape_item.url.parts:
                await self.user(scrape_item, reddit)
            elif "r" in scrape_item.url.parts and "comments" not in scrape_item.url.parts:
                await self.subreddit(scrape_item, reddit)
            elif "redd.it" in scrape_item.url.host:
                await self.media(scrape_item, reddit)
            else:
                log(f"Scrape Failed: Unknown URL Path for {scrape_item.url}", 40)
                self.manager.progress_manager.scrape_stats_progress.add_failure("Unknown")

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, reddit: asyncpraw.Reddit) -> None:
        """Scrapes user pages."""
        username = scrape_item.url.name or scrape_item.url.parts[-2]
        title = self.create_title(username, None, None)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True

        user: Redditor = await reddit.redditor(username)
        submissions: AsyncIterator[Submission] = user.submissions.new(limit=None)
        await self.get_posts(scrape_item, submissions, reddit)

    @error_handling_wrapper
    async def subreddit(self, scrape_item: ScrapeItem, reddit: asyncpraw.Reddit) -> None:
        """Scrapes subreddit pages."""
        subreddit = scrape_item.url.name or scrape_item.url.parts[-2]
        title = self.create_title(subreddit, None, None)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True

        subreddit: Subreddit = await reddit.subreddit(subreddit)
        submissions: AsyncIterator[Submission] = subreddit.new(limit=None)
        await self.get_posts(scrape_item, submissions, reddit)

    @error_handling_wrapper
    async def get_posts(
        self,
        scrape_item: ScrapeItem,
        submissions: AsyncIterator[Submission],
        reddit: asyncpraw.Reddit,
    ) -> None:
        try:
            submissions_list: list[Subreddit] = [submission async for submission in submissions]
        except asyncprawcore.exceptions.Forbidden:
            raise ScrapeError(403, origin=scrape_item) from None
        except asyncprawcore.exceptions.NotFound:
            raise ScrapeError(404, origin=scrape_item) from None

        scrape_item.type = FILE_HOST_PROFILE
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = (
                self.manager.config_manager.settings_data.download_options.maximum_number_of_children[scrape_item.type]
            )

        for submission in submissions_list:
            await self.post(scrape_item, submission, reddit)
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, submission: Submission, reddit: asyncpraw.Reddit) -> None:
        """Scrapes posts."""
        title = submission.title
        date = int(str(submission.created_utc).split(".")[0])

        try:
            media_url = URL(submission.media["reddit_video"]["fallback_url"])
        except (KeyError, TypeError):
            media_url = URL(submission.url)

        if "v.redd.it" in media_url.host:
            filename, ext = get_filename_and_ext(media_url.name)

        if "redd.it" in media_url.host:
            new_scrape_item = await self.create_new_scrape_item(
                media_url,
                scrape_item,
                title,
                date,
                add_parent=scrape_item.url,
            )
            await self.media(new_scrape_item, reddit)
        elif "gallery" in media_url.parts:
            new_scrape_item = await self.create_new_scrape_item(
                media_url,
                scrape_item,
                title,
                date,
                add_parent=scrape_item.url,
            )
            await self.gallery(new_scrape_item, submission, reddit)
        elif "reddit.com" not in media_url.host:
            new_scrape_item = await self.create_new_scrape_item(
                media_url,
                scrape_item,
                title,
                date,
                add_parent=scrape_item.url,
            )
            self.handle_external_links(new_scrape_item)

    async def gallery(self, scrape_item: ScrapeItem, submission: Submission, reddit: asyncpraw.Reddit) -> None:
        """Scrapes galleries."""
        if not hasattr(submission, "media_metadata") or submission.media_metadata is None:
            return
        items = [item for item in submission.media_metadata.values() if item["status"] == "valid"]
        links = [URL(item["s"]["u"]).with_host("i.redd.it").with_query(None) for item in items]
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = (
                self.manager.config_manager.settings_data.download_options.maximum_number_of_children[scrape_item.type]
            )
        for link in links:
            new_scrape_item = await self.create_new_scrape_item(
                link,
                scrape_item,
                scrape_item.parent_title,
                scrape_item.possible_datetime,
                add_parent=scrape_item.url,
            )
            await self.media(new_scrape_item, reddit)
            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem, reddit: asyncpraw.Reddit) -> None:
        """Handles media links."""
        try:
            filename, ext = get_filename_and_ext(scrape_item.url.name)
        except NoExtensionError:
            head = await self.client.get_head(self.domain, scrape_item.url)
            head = await self.client.get_head(self.domain, head["location"])

            try:
                post = await reddit.submission(url=head["location"])
            except asyncprawcore.exceptions.Forbidden:
                raise ScrapeError(403, "Forbidden", origin=scrape_item) from None
            except asyncprawcore.exceptions.NotFound:
                raise ScrapeError(404, "Not Found", origin=scrape_item) from None

            await self.post(scrape_item, post, reddit)
            return

        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def create_new_scrape_item(
        self,
        link: URL,
        old_scrape_item: ScrapeItem,
        title: str,
        date: int,
        add_parent: URL | None = None,
    ) -> ScrapeItem:
        """Creates a new scrape item with the same parent as the old scrape item."""
        new_scrape_item = self.create_scrape_item(
            old_scrape_item,
            link,
            "",
            True,
            None,
            date,
            add_parent=add_parent,
        )
        if self.manager.config_manager.settings_data.download_options.separate_posts:
            new_scrape_item.add_to_parent_title(title)
        return new_scrape_item
