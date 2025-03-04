from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import aiohttp
import asyncprawcore
from aiohttp_client_cache import CachedSession
from aiolimiter import AsyncLimiter
from asyncpraw import Reddit
from yarl import URL

from cyberdrop_dl.clients.errors import LoginError, NoExtensionError, ScrapeError
from cyberdrop_dl.clients.scraper_client import cache_control_manager
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.logger import log, log_debug
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
        self.trace_configs = []

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        await self.check_login(self.primary_base_domain / "login")
        if self.logged_in:
            self.add_request_log_hooks()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if not self.logged_in:
            return

        assert scrape_item.url.host
        async with CachedSession(
            cache=self.manager.cache_manager.request_cache, trace_configs=self.trace_configs
        ) as session:
            await cache_control_manager(session)
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
                new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, add_parent=scrape_item.url)
                await self.post(new_scrape_item, submission, reddit)
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
        scrape_item.possible_datetime = date
        post = Post(title=title, date=date)
        self.add_separate_post_title(scrape_item, post)  # type: ignore
        await self.process_item(scrape_item, submission, reddit, link)

    @error_handling_wrapper
    async def process_item(self, scrape_item: ScrapeItem, submission: Submission, reddit: Reddit, link: URL) -> None:
        assert link.host
        if "redd.it" in link.host:
            return await self.media(scrape_item, reddit, link)

        new_scrape_item = self.create_scrape_item(scrape_item, link)
        if "gallery" in link.parts:
            return await self.gallery(new_scrape_item, submission, reddit)
        if "reddit.com" not in link.host:
            return self.handle_external_links(new_scrape_item)
        origin = scrape_item.origin()
        parent = scrape_item.parent()
        msg = f"found on {parent}"
        if parent != origin:
            msg += f" from {origin}"
        log(f"Skipping nested thread URL {link} {msg}", 10)

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
            await self.media(scrape_item, reddit, link)
            scrape_item.add_children()

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem, reddit: Reddit, link: URL | None = None) -> None:
        """Handles media links."""
        url = link or scrape_item.url
        try:
            filename, ext = get_filename_and_ext(url.name)
        except NoExtensionError:
            url = await self.get_final_location(url)
            scrape_item.url = url
            with asyncpraw_error_handle(scrape_item):
                post = await reddit.submission(url=str(url))

            return await self.post(scrape_item, post, reddit)

        await self.handle_file(url, scrape_item, filename, ext)

    async def get_final_location(self, url) -> URL:
        headers = await self.client.get_head(self.domain, url)
        content_type = headers.get("Content-Type", "")
        if any(s in content_type.lower() for s in ("html", "text")):
            _, url = await self.client.get_soup_and_return_url(self.domain, url)
            return url
        location = headers.get("location")
        if not location:
            raise ScrapeError(422)
        return self.parse_url(location)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def add_request_log_hooks(self) -> None:
        async def on_request_start(*args):
            params: aiohttp.TraceRequestStartParams = args[2]
            log_debug(f"Starting reddit {params.method} request to {params.url}", 10)

        async def on_request_end(*args):
            params: aiohttp.TraceRequestEndParams = args[2]
            msg = f"Finishing reddit {params.method} request to {params.url}"
            msg += f" -> response status: {params.response.status}"
            log_debug(msg, 10)

        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(on_request_start)
        trace_config.on_request_end.append(on_request_end)
        self.trace_configs.append(trace_config)

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
