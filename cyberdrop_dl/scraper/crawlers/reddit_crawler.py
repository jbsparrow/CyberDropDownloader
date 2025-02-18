from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import asyncpraw
import asyncprawcore
from aiohttp_client_cache import CachedSession
from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from asyncpraw.models import Redditor, Submission, Subreddit

    from cyberdrop_dl.managers.manager import Manager


@dataclass
class Post:
    title: str
    date: int
    id: int = None

    @property
    def number(self) -> int:
        return self.id


class RedditCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"reddit": ["reddit", "redd.it"]}
    DEFAULT_POST_TITLE_FORMAT = "{title}"
    primary_base_domain = URL("https://www.reddit.com/")

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, "Reddit")
        self.reddit_personal_use_script = self.manager.config_manager.authentication_data.reddit.personal_use_script
        self.reddit_secret = self.manager.config_manager.authentication_data.reddit.secret
        self.request_limiter = AsyncLimiter(5, 1)
        self.logged_in = False

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        self.logged_in = self.reddit_personal_use_script and self.reddit_secret
        if not self.logged_in:
            log("Reddit API credentials not found. Skipping.", 40)

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if not self.logged_in:
            return

        async with CachedSession(cache=self.manager.cache_manager.request_cache) as reddit_session:
            reddit = asyncpraw.Reddit(
                client_id=self.reddit_personal_use_script,
                client_secret=self.reddit_secret,
                user_agent="CyberDrop-DL",
                requestor_kwargs={"session": reddit_session},
                check_for_updates=False,
            )

            if any(part in scrape_item.url.parts for part in ("user", "u")):
                await self.user(scrape_item, reddit)
            elif any(part in scrape_item.url.parts for part in ("comments", "r")):
                await self.subreddit(scrape_item, reddit)
            elif "redd.it" in scrape_item.url.host:
                await self.media(scrape_item, reddit)
            else:
                raise ValueError

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, reddit: asyncpraw.Reddit) -> None:
        """Scrapes user pages."""
        username = scrape_item.url.parts[-2] if len(scrape_item.url.parts) > 3 else scrape_item.url.name
        title = self.create_title(username)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True

        user: Redditor = await reddit.redditor(username)
        submissions: AsyncIterator[Submission] = user.submissions.new(limit=None)
        await self.get_posts(scrape_item, submissions, reddit)

    @error_handling_wrapper
    async def subreddit(self, scrape_item: ScrapeItem, reddit: asyncpraw.Reddit) -> None:
        """Scrapes subreddit pages."""
        subreddit: str = scrape_item.url.name or scrape_item.url.parts[-2]
        title = self.create_title(subreddit)
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

        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)

        for submission in submissions_list:
            await self.post(scrape_item, submission, reddit)
            scrape_item.add_children()

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, submission: Submission, reddit: asyncpraw.Reddit) -> None:
        """Scrapes posts."""
        title = submission.title
        date = int(str(submission.created_utc).split(".")[0])

        try:
            media_url_str = submission.media["reddit_video"]["fallback_url"]
        except (KeyError, TypeError):
            media_url_str = submission.url

        media_url = self.parse_url(media_url_str)

        new_scrape_item = await self.create_new_scrape_item(
            media_url,
            scrape_item,
            title,
            date=date,
            add_parent=scrape_item.url,
        )

        await self.process_item(new_scrape_item, submission, reddit)

    @error_handling_wrapper
    async def process_item(self, scrape_item: ScrapeItem, submission: Submission, reddit: asyncpraw.Reddit) -> None:
        if "redd.it" in scrape_item.url.host:
            return await self.media(scrape_item, reddit)
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item, submission, reddit)
        if "reddit.com" not in scrape_item.url.host:
            return self.handle_external_links(scrape_item)
        log(f"Skipping nested thread URL {scrape_item.url} found on {scrape_item.parents[0]}", 10)

    async def gallery(self, scrape_item: ScrapeItem, submission: Submission, reddit: asyncpraw.Reddit) -> None:
        """Scrapes galleries."""
        if not hasattr(submission, "media_metadata") or submission.media_metadata is None:
            return
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        for item in submission.media_metadata.values():
            if item["status"] != "valid":
                continue
            link_str = item["s"]["u"]
            link = self.parse_url(link_str).with_host("i.redd.it").with_query(None)
            new_scrape_item = await self.create_new_scrape_item(
                link,
                scrape_item,
                scrape_item.parent_title,
                scrape_item.possible_datetime,
                add_parent=scrape_item.url,
            )
            await self.media(new_scrape_item, reddit)
            scrape_item.add_children()

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
                raise ScrapeError(403, origin=scrape_item) from None
            except asyncprawcore.exceptions.NotFound:
                raise ScrapeError(404, origin=scrape_item) from None

            return await self.post(scrape_item, post, reddit)

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
        post = Post(title=title, date=date)
        new_scrape_item = self.create_scrape_item(
            old_scrape_item,
            link,
            part_of_album=True,
            possible_datetime=date,
            add_parent=add_parent,
        )
        self.add_separate_post_title(new_scrape_item, post)
        return new_scrape_item
