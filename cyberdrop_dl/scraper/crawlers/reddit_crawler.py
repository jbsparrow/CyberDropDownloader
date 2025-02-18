from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import asyncprawcore
from aiohttp_client_cache import CachedSession
from aiolimiter import AsyncLimiter
from asyncpraw import Reddit
from yarl import URL

from cyberdrop_dl.clients.errors import LoginError, NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator

    from asyncpraw.models import Redditor, Submission, Subreddit

    from cyberdrop_dl.managers.manager import Manager


@dataclass
class Post:
    title: str
    date: int
    id: int = None  # type: ignore

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
        await self.check_login(self.primary_base_domain / "login")

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if not self.logged_in:
            return

        assert scrape_item.url.host
        async with CachedSession(cache=self.manager.cache_manager.request_cache) as session:
            reddit = self.new_reddit_conn(session)
            if any(part in scrape_item.url.parts for part in ("user", "u")):
                return await self.user(scrape_item, reddit)
            if any(part in scrape_item.url.parts for part in ("comments", "r")):
                return await self.subreddit(scrape_item, reddit)
            if "redd.it" in scrape_item.url.host:
                return await self.media(scrape_item, reddit)
            raise ValueError

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, reddit: Reddit) -> None:
        """Scrapes user pages."""
        username = scrape_item.url.parts[-2] if len(scrape_item.url.parts) > 3 else scrape_item.url.name
        title = self.create_title(username)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True

        user: Redditor = await reddit.redditor(username)
        submissions: AsyncIterator[Submission] = user.submissions.new(limit=None)
        await self.get_posts(scrape_item, submissions, reddit)

    @error_handling_wrapper
    async def subreddit(self, scrape_item: ScrapeItem, reddit: Reddit) -> None:
        """Scrapes subreddit pages."""
        subreddit_name: str = scrape_item.url.name or scrape_item.url.parts[-2]
        title = self.create_title(subreddit_name)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True

        subreddit: Subreddit = await reddit.subreddit(subreddit_name)
        submissions: AsyncIterator[Submission] = subreddit.new(limit=None)  # type: ignore
        await self.get_posts(scrape_item, submissions, reddit)

    @error_handling_wrapper
    async def get_posts(self, scrape_item: ScrapeItem, submissions: AsyncIterator[Submission], reddit: Reddit) -> None:
        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)

        with asyncpraw_error_handle(scrape_item):
            async for submission in submissions:
                await self.post(scrape_item, submission, reddit)
                scrape_item.add_children()

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, submission: Submission, reddit: Reddit) -> None:
        """Scrapes posts."""
        title = submission.title
        date = int(str(submission.created_utc).split(".")[0])

        try:
            link_str: str = submission.media["reddit_video"]["fallback_url"]
        except (KeyError, TypeError):
            link_str = submission.url

        link = self.parse_url(link_str)
        new_scrape_item = self.create_scrape_item(scrape_item, link, possible_datetime=date, add_parent=scrape_item.url)
        post = Post(title=title, date=date)
        self.add_separate_post_title(new_scrape_item, post)  # type: ignore
        await self.process_item(new_scrape_item, submission, reddit)

    @error_handling_wrapper
    async def process_item(self, scrape_item: ScrapeItem, submission: Submission, reddit: Reddit) -> None:
        assert scrape_item.url.host
        if "redd.it" in scrape_item.url.host:
            return await self.media(scrape_item, reddit)
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item, submission, reddit)
        if "reddit.com" not in scrape_item.url.host:
            return self.handle_external_links(scrape_item)
        log(f"Skipping nested thread URL {scrape_item.url} found on {scrape_item.parents[0]}", 10)

    async def gallery(self, scrape_item: ScrapeItem, submission: Submission, reddit: Reddit) -> None:
        """Scrapes galleries."""
        if not hasattr(submission, "media_metadata") or submission.media_metadata is None:
            return

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        for item in submission.media_metadata.values():
            if item["status"] != "valid":
                continue
            link_str = item["s"]["u"]
            link = self.parse_url(link_str).with_host("i.redd.it").with_query(None)
            new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
            post = Post(title=scrape_item.parent_title, date=scrape_item.possible_datetime)  # type: ignore
            self.add_separate_post_title(new_scrape_item, post)  # type: ignore
            await self.media(new_scrape_item, reddit)
            scrape_item.add_children()

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem, reddit: Reddit) -> None:
        """Handles media links."""
        try:
            filename, ext = get_filename_and_ext(scrape_item.url.name)
        except NoExtensionError:
            _, url = await self.client.get_soup_and_return_url(self.domain, scrape_item.url)

            with asyncpraw_error_handle(scrape_item):
                post = await reddit.submission(url=str(url))

            return await self.post(scrape_item, post, reddit)

        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def new_reddit_conn(self, client_session):
        return Reddit(
            client_id=self.reddit_personal_use_script,
            client_secret=self.reddit_secret,
            user_agent="CyberDrop-DL",
            requestor_kwargs={"session": client_session},
            check_for_updates=False,
        )

    @error_handling_wrapper
    async def check_login(self, _) -> None:
        if not (self.reddit_personal_use_script and self.reddit_secret):
            msg = "Reddit API credentials were not provided"
            raise LoginError(message=msg)
        self.logged_in = True


@contextmanager
def asyncpraw_error_handle(scrape_item: ScrapeItem) -> Generator:
    try:
        yield
    except asyncprawcore.exceptions.Forbidden:
        raise ScrapeError(403, origin=scrape_item) from None
    except asyncprawcore.exceptions.NotFound:
        raise ScrapeError(404, origin=scrape_item) from None
