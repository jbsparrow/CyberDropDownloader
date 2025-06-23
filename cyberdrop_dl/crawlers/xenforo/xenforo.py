# ruff : noqa: RUF009

from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup

from cyberdrop_dl.crawlers._forum import (
    HTMLMessageBoardCrawler,
    MessageBoardSelectors,
    PostSelectors,
    Thread,
    parse_thread,
)
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import LoginError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import (
    error_handling_wrapper,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from cyberdrop_dl.crawlers.crawler import SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


Selector = css.CssAttributeSelector


@dataclasses.dataclass(frozen=True, slots=True)
class XenforoPostSelectors(PostSelectors):
    article: str = "article.message[id*=post]"
    content: str = ".message-userContent"
    article_trash: tuple[str, ...] = (
        ".message-signature",
        ".message-footer",
    )
    content_trash: tuple[str, ...] = ("blockquote",)
    id: Selector = Selector(article, "id")
    attachments: Selector = Selector(".message-attachments a[href]", "href")


DEFAULT_XF_POST_SELECTORS = XenforoPostSelectors()


@dataclasses.dataclass(frozen=True, slots=True)
class XenforoMessageBoardSelectors(MessageBoardSelectors):
    posts: XenforoPostSelectors = DEFAULT_XF_POST_SELECTORS
    confirmation_button: Selector = Selector("a[class*=button--cta][href]", "href")
    next_page: Selector = Selector("a[class*=pageNav-jump--next][href]", "href")
    title_trash: Selector = Selector("span")
    title: Selector = Selector("h1[class*=p-title-value]")
    last_page: Selector = Selector("li.pageNav-page a:last-of-type", "href")
    current_page: Selector = Selector("li.pageNav-page.pageNav-page--current a", "href")


DEFAULT_XF_SELECTORS = XenforoMessageBoardSelectors()
KNOWN_THREAD_PART_NAMES = "thread", "topic", "tema"
KNOWN_THREAD_PART_NAMES = ",".join(f"{part},{part}s" for part in KNOWN_THREAD_PART_NAMES).split(",")


def _escape(strings: Iterable[str]) -> str:
    return r"\|".join(strings)


class XenforoCrawler(HTMLMessageBoardCrawler, is_abc=True):
    ATTACHMENT_URL_PARTS = "attachments", "data", "uploads"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Attachments": f"/({_escape(ATTACHMENT_URL_PARTS)})/...",
        "Threads": (
            f"/({_escape(KNOWN_THREAD_PART_NAMES)})/<thread_name_and_id>",
            "/posts/<post_id>",
            "/goto/<post_id>",
        ),
        "**NOTE**": "base crawler: Xenforo",
    }
    SUPPORTS_THREAD_RECURSION: ClassVar[bool] = True
    SELECTORS: ClassVar[MessageBoardSelectors] = DEFAULT_XF_SELECTORS
    POST_URL_PART_NAME: ClassVar[str] = "post"
    PAGE_URL_PART_NAME: ClassVar[str] = "page"
    LOGIN_USER_COOKIE_NAME = "xf_user"
    ATTACHMENT_HOSTS = "smgmedia", "attachments.f95zone"
    THREAD_PART_NAMES: ClassVar[Sequence[str]] = KNOWN_THREAD_PART_NAMES
    IGNORE_EMBEDED_IMAGES_SRC = True
    login_required = True

    def get_filename_and_ext(self, filename: str) -> tuple[str, str]:
        return super().get_filename_and_ext(filename, forum=True)

    @classmethod
    def parse_thread(cls, url: AbsoluteHttpURL, thread_name_and_id: str) -> Thread:
        return parse_thread(url, thread_name_and_id, cls.PAGE_URL_PART_NAME, cls.POST_URL_PART_NAME)

    @classmethod
    def make_post_url(cls, thread: Thread, post_id: int) -> AbsoluteHttpURL:
        return thread.url / f"{cls.POST_URL_PART_NAME}-{post_id}"

    @error_handling_wrapper
    async def xf_login(self, login_url: AbsoluteHttpURL, session_cookie: str, username: str, password: str) -> None:
        """Logs in to a forum."""
        manual_login = username and password
        missing_credentials = not (manual_login or session_cookie)
        if missing_credentials:
            msg = f"Login info wasn't provided for {self.FOLDER_DOMAIN}"
            raise LoginError(message=msg)

        if session_cookie:
            cookies = {"xf_user": session_cookie}
            self.update_cookies(cookies)

        credentials = {"login": username, "password": password, "_xfRedirect": str(self.PRIMARY_URL)}
        await self.xf_try_login(login_url, credentials, retries=5)

    async def xf_try_login(
        self,
        login_url: AbsoluteHttpURL,
        credentials: dict[str, str],
        retries: int,
        wait_time: int | None = None,
    ) -> None:
        # Try from cookies
        text, logged_in = await self.check_login_with_request(login_url)
        if logged_in:
            self.logged_in = True
            return

        wait_time = wait_time or retries
        attempt = 0
        while attempt < retries:
            try:
                attempt += 1
                await asyncio.sleep(wait_time)
                data = parse_login_form(text) | credentials
                _ = await self.client._post_data(self.DOMAIN, login_url / "login", data=data, cache_disabled=True)
                await asyncio.sleep(wait_time)
                text, logged_in = await self.check_login_with_request(login_url)
                if logged_in:
                    self.logged_in = True
                    return
            except TimeoutError:
                continue
        msg = f"Failed to login on {self.FOLDER_DOMAIN} after {retries} attempts"
        raise LoginError(message=msg)

    async def check_login_with_request(self, login_url: AbsoluteHttpURL) -> tuple[str, bool]:
        text = await self.client.get_text(self.DOMAIN, login_url, cache_disabled=True)
        return text, any(p in text for p in ('<span class="p-navgroup-user-linkText">', "You are already logged in."))


def parse_login_form(resp_text: str) -> dict[str, str]:
    soup = BeautifulSoup(resp_text, "html.parser")
    inputs = soup.select("form:first-of-type input")
    data = {
        name: value
        for elem in inputs
        if (name := css.get_attr_or_none(elem, "name")) and (value := css.get_attr_or_none(elem, "value"))
    }
    if data:
        return data
    raise ScrapeError(422)
