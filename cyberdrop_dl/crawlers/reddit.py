from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, ClassVar, NotRequired, TypedDict

import asyncprawcore
from asyncpraw import Reddit

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import LoginError, NoExtensionError, ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator

    from asyncpraw.models import Redditor, Submission, Subreddit

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class MediaFile(TypedDict):
    y: int  # Height
    x: int  # Width


class MediaSource(MediaFile):
    u: NotRequired[str]  # URL
    gif: NotRequired[str]  # URL
    mp4: NotRequired[str]  # URL


class MediaMetadata(TypedDict):
    status: str
    m: str  # mimetype
    p: list[MediaFile]  # Previews
    o: list[MediaFile]  # Originals? Options?
    s: MediaSource  # Source


PRIMARY_URL = AbsoluteHttpURL("https://www.reddit.com/")


class RedditCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "User": ("/user/<user>", "/user/<user>/...", "/u/<user>"),
        "Subreddit:": "/r/<subreddit>",
        "Direct links": "",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "reddit", "redd.it"
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{title}"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "reddit"
    _RATE_LIMIT = 5, 1

    def __post_init__(self) -> None:
        self.reddit_personal_use_script = self.manager.config_manager.authentication_data.reddit.personal_use_script
        self.reddit_secret = self.manager.config_manager.authentication_data.reddit.secret
        self.logged_in = False

    async def async_startup(self) -> None:
        await self.check_login(PRIMARY_URL / "login")
        if not self.logged_in:
            return

        self._session = self.manager.client_manager.reddit_session
        self._reddit = Reddit(
            client_id=self.reddit_personal_use_script,
            client_secret=self.reddit_secret,
            user_agent="CyberDrop-DL",
            requestor_kwargs={"session": self._session},
            check_for_updates=False,
        )

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if not self.logged_in:
            return

        async with self.client.client_manager.cache_control(self._session):
            if any(part in scrape_item.url.parts for part in ("user", "u")):
                return await self.user(scrape_item)
            if any(part in scrape_item.url.parts for part in ("comments", "r")):
                return await self.subreddit(scrape_item)
            if "redd.it" in scrape_item.url.host:
                return await self.media(scrape_item)
            raise ValueError

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem) -> None:
        username = scrape_item.url.parts[-2] if len(scrape_item.url.parts) > 3 else scrape_item.url.name
        title = self.create_title(username)
        scrape_item.setup_as_profile(title)
        user: Redditor = await self._reddit.redditor(username)
        submissions: AsyncIterator[Submission] = user.submissions.new(limit=None)
        await self.get_posts(scrape_item, submissions)

    @error_handling_wrapper
    async def subreddit(self, scrape_item: ScrapeItem) -> None:
        subreddit_name: str = scrape_item.url.name or scrape_item.url.parts[-2]
        title = self.create_title(subreddit_name)
        scrape_item.setup_as_profile(title)
        subreddit: Subreddit = await self._reddit.subreddit(subreddit_name)
        submissions: AsyncIterator[Submission] = subreddit.new(limit=None)  # type: ignore[reportArgumentType]
        await self.get_posts(scrape_item, submissions)

    @error_handling_wrapper
    async def get_posts(self, scrape_item: ScrapeItem, submissions: AsyncIterator[Submission]) -> None:
        with asyncpraw_error_handle():
            async for submission in submissions:
                new_scrape_item = scrape_item.copy()
                await self.post(new_scrape_item, submission)
                scrape_item.add_children()

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, submission: Submission) -> None:
        try:
            link_str: str = submission.media["reddit_video"]["fallback_url"]
        except (KeyError, TypeError):
            link_str = submission.url

        link = self.parse_url(link_str)
        date = int(str(submission.created_utc).split(".")[0])
        scrape_item.possible_datetime = date
        scrape_item.setup_as_post("")
        post_title = self.create_separate_post_title(submission.title, submission.id, date)
        scrape_item.add_to_parent_title(post_title)
        await self.process_item(scrape_item, submission, link)

    @error_handling_wrapper
    async def process_item(self, scrape_item: ScrapeItem, submission: Submission, link: AbsoluteHttpURL) -> None:
        if "redd.it" in link.host:
            return await self.media(scrape_item, link)

        new_scrape_item = scrape_item.create_child(link)
        if "gallery" in link.parts:
            return await self.gallery(new_scrape_item, submission)
        if "reddit.com" not in link.host:
            return self.handle_external_links(new_scrape_item)

        msg = f"found on {scrape_item.parent}"
        if scrape_item.parent != scrape_item.origin:
            msg += f" from {scrape_item.origin}"
        self.log(f"Skipping nested thread URL {link} {msg}")

    async def gallery(self, scrape_item: ScrapeItem, submission: Submission) -> None:
        media_metadata: dict[str, MediaMetadata] = getattr(submission, "media_metadata", {})
        if not media_metadata:
            return

        for item in media_metadata.values():
            if item["status"] != "valid":
                continue
            source = item["s"]
            link_str = source.get("u") or source.get("gif") or source.get("mp4")
            if not link_str:
                # TODO: Move this logic to its own method so we can raise an error on each individual link
                continue
            link = self.parse_url(link_str).with_host("i.redd.it").with_query(None)
            await self.media(scrape_item, link)
            scrape_item.add_children()

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL | None = None) -> None:
        """Handles media links."""
        url = link or scrape_item.url
        try:
            filename, ext = self.get_filename_and_ext(url.name)
        except NoExtensionError:
            async with self.request(url) as resp:
                if url == resp.url:
                    raise
                scrape_item.url = url = resp.url
            with asyncpraw_error_handle():
                post = await self._reddit.submission(url=str(url))

            return await self.post(scrape_item, post)

        await self.handle_file(url, scrape_item, filename, ext)

    @error_handling_wrapper
    async def check_login(self, _) -> None:
        if not (self.reddit_personal_use_script and self.reddit_secret):
            msg = "Reddit API credentials were not provided"
            raise LoginError(message=msg)
        self.logged_in = True


@contextmanager
def asyncpraw_error_handle() -> Generator[None]:
    try:
        yield
    except asyncprawcore.exceptions.ResponseException as e:
        raise ScrapeError(e.response.status, message=str(e)) from None
    except asyncprawcore.exceptions.AsyncPrawcoreException as e:
        raise ScrapeError(422, message=str(e)) from None
