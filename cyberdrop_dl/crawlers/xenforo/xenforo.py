"""Generic crawler for any Xenforo

A Xenforo site has these attributes attached to the main html tag of the site:
id="XF"                                  This identifies the site as a Xenforo site
data-cookie-prefix="ogaddgmetaprof_"     The full cookies name will be `ogaddgmetaprof_user`
data-xf="2.3"                            Version number


Xenforo sites have a REST API but the APi is private only. Admins of the site need to grand access user by user
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup

from cyberdrop_dl.crawlers._forum import HTMLMessageBoardCrawler, MessageBoardSelectors, PostSelectors
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import LoginError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from cyberdrop_dl.crawlers.crawler import SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


Selector = css.CssAttributeSelector


DEFAULT_XF_POST_SELECTORS = PostSelectors(
    article="article.message[id*=post]",
    content=".message-userContent",
    article_trash=(".message-signature", ".message-footer"),
    content_trash=("blockquote", "fauxBlockLink"),
    id=Selector("article.message[id*=post]", "id"),
    attachments=Selector(".message-attachments a[href]", "href"),
)


DEFAULT_XF_SELECTORS = MessageBoardSelectors(
    posts=DEFAULT_XF_POST_SELECTORS,
    confirmation_button=Selector("a[class*=button--cta][href]", "href"),
    next_page=Selector("a[class*=pageNav-jump--next][href]", "href"),
    title_trash=("span",),
    title=Selector("h1[class*=p-title-value]"),
    last_page=Selector("li.pageNav-page a:last-of-type", "href"),
    current_page=Selector("li.pageNav-page.pageNav-page--current a", "href"),
)


def _escape(strings: Iterable[str]) -> str:
    return r"\|".join(strings)


class XenforoCrawler(HTMLMessageBoardCrawler, is_abc=True):
    ATTACHMENT_URL_PARTS = "attachments", "data", "uploads"
    THREAD_PART_NAMES: ClassVar[Sequence[str]] = "thread", "topic", "tema", "threads", "topics", "temas"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Attachments": f"/({_escape(ATTACHMENT_URL_PARTS)})/...",
        "Threads": (
            f"/({_escape(THREAD_PART_NAMES)})/<thread_name_and_id>",
            "/posts/<post_id>",
            "/goto/<post_id>",
        ),
        "**NOTE**": "base crawler: Xenforo",
    }
    SUPPORTS_THREAD_RECURSION: ClassVar[bool] = True
    SELECTORS: ClassVar[MessageBoardSelectors] = DEFAULT_XF_SELECTORS
    POST_URL_PART_NAME: ClassVar[str] = "post"
    PAGE_URL_PART_NAME: ClassVar[str] = "page"
    IGNORE_EMBEDED_IMAGES_SRC: ClassVar[bool] = True
    LOGIN_USER_COOKIE_NAME: ClassVar[str] = "xf_user"
    # Attachments hosts should technically be defined on each specific Crawler, but they do no harm here
    ATTACHMENT_HOSTS = "smgmedia", "attachments.f95zone"
    login_required = True

    def get_filename_and_ext(self, filename: str) -> tuple[str, str]:
        # The `forum` keyword is misleading now. It only works for Xenforo sites, not every forum
        # TODO: Change `forum` parameter to `xenforo`
        return super().get_filename_and_ext(filename, forum=True)

    @error_handling_wrapper
    async def xf_login(self, login_url: AbsoluteHttpURL, session_cookie: str, username: str, password: str) -> None:
        """Logic to login as a Xenforo user

        This was deprecated in v6.5.0 but the code itself it useful for debuggig without cookie extraction.
        Login functionality may come back in a future version..."""

        manual_login = username and password
        missing_credentials = not (manual_login or session_cookie)
        if missing_credentials:
            msg = f"Login info wasn't provided for {self.FOLDER_DOMAIN}"
            raise LoginError(message=msg)

        if session_cookie:
            cookies = {self.LOGIN_USER_COOKIE_NAME: session_cookie}
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
        # Check first if we have cookies and they are valid
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
