from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import datetime
from json import dumps as json_dumps
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import cyberdrop_dl.constants as constants
from cyberdrop_dl.clients.response import AbstractResponse
from cyberdrop_dl.exceptions import DDOSGuardError
from cyberdrop_dl.utils.cookie_management import make_simple_cookie
from cyberdrop_dl.utils.utilities import sanitize_filename

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from curl_cffi.requests.impersonate import BrowserTypeLiteral
    from curl_cffi.requests.session import HttpMethod

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
    from cyberdrop_dl.managers.client_manager import ClientManager


class ScraperClient:
    """AIOHTTP / CURL operations for scraping."""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self._save_pages_html = client_manager.manager.config_manager.settings_data.files.save_pages_html
        self._pages_folder = self.client_manager.manager.path_manager.pages_folder
        min_html_file_path_len = len(str(self._pages_folder)) + len(constants.STARTUP_TIME_STR) + 10
        self._max_html_stem_len = 245 - min_html_file_path_len

    @contextlib.asynccontextmanager
    async def _limiter(self, domain: str) -> AsyncGenerator[None]:
        with self.client_manager.request_context(domain):
            domain_limiter = self.client_manager.get_rate_limiter(domain)
            async with self.client_manager.global_rate_limiter, domain_limiter:
                await self.client_manager.manager.states.RUNNING.wait()
                yield

    @contextlib.asynccontextmanager
    async def _request(
        self: object,
        url: AbsoluteHttpURL,
        /,
        method: HttpMethod = "GET",
        headers: dict[str, str] | None = None,
        impersonate: BrowserTypeLiteral | bool | None = None,
        data: Any = None,
        json: Any = None,
        cache_disabled: bool = False,
        **request_params: Any,
    ) -> AsyncGenerator[AbstractResponse]:
        """
        Asynchronous context manager for HTTP requests.

        - If 'impersonate' is specified, uses curl_cffi for the request and updates cookies.
        - Otherwise, uses aiohttp with optional cache control.
        - Yield an AbstractResponse that wraps the underlying response with common methods.
        - On DDOSGuardError, retries the request using FlareSolverr.
        - Saves the HTML content to disk if the config option is enabled.
        - Closes underliying response on exit.
        """
        self = cast("ScraperClient", self)
        request_params["headers"] = self.client_manager._default_headers | (headers or {})
        request_params["data"] = data
        request_params["json"] = json

        async with self.__request_context(url, method, request_params, impersonate, cache_disabled) as resp:
            exc = None
            try:
                yield await self._check_response(resp, url)
            except Exception as e:
                exc = e
                raise
            finally:
                await self.write_soup_to_disk(url, resp, exc)

    def __sync_session_cookies(self, url: AbsoluteHttpURL) -> None:
        """
        Apply to the cookies from the `curl` session into the `aiohttp` session, filtering them by the URL

        This is mostly just to get the `cf_cleareance` cookie value into the `aiohttp` session

        The reverse (sync `aiohttp` -> `curl`) is not needed at the moment, so it is skipped
        """
        now = time.time()
        for cookie in self.client_manager._curl_session.cookies.jar:
            simple_cookie = make_simple_cookie(cookie, now)
            self.client_manager.cookies.update_cookies(simple_cookie, url)

    @contextlib.asynccontextmanager
    async def __request_context(
        self,
        url: AbsoluteHttpURL,
        method: HttpMethod,
        request_params: dict[str, Any],
        impersonate: BrowserTypeLiteral | bool | None,
        cache_disabled: bool,
    ) -> AsyncGenerator[AbstractResponse]:
        impersonate = self.client_manager.manager.parsed_args.cli_only_args.impersonate or impersonate
        if impersonate:
            self.client_manager.check_curl_cffi_is_available()
            if impersonate is True:
                impersonate = "chrome"
            request_params["impersonate"] = impersonate
            curl_resp = await self.client_manager._curl_session.request(method, str(url), stream=True, **request_params)
            try:
                yield AbstractResponse.from_resp(curl_resp)
                self.__sync_session_cookies(url)
            finally:
                await curl_resp.aclose()
            return

        async with (
            self.client_manager.cache_control(self.client_manager._session, disabled=cache_disabled),
            self.client_manager._session.request(method, url, **request_params) as aio_resp,
        ):
            yield AbstractResponse.from_resp(aio_resp)

    async def _check_response(self, abs_resp: AbstractResponse, url: AbsoluteHttpURL, data: Any | None = None):
        """Checks the HTTP response status and retries DDOS Guard errors with FlareSolverr.

        Returns an AbstractResponse confirmed to not be a DDOS Guard page."""
        try:
            await self.client_manager.check_http_status(abs_resp)
            return abs_resp
        except DDOSGuardError:
            flare_solution = await self.client_manager.flaresolverr.request(url, data)
            return AbstractResponse.from_flaresolverr(flare_solution)

    async def write_soup_to_disk(self, url: AbsoluteHttpURL, response: AbstractResponse, exc: Exception | None = None):
        """Writes html to a file."""

        if not (
            self._save_pages_html
            and "html" in response.content_type
            and response.consumed  # Do not consume the response if the crawler didn't
        ):
            return

        content = cast("str", (await response.soup()).prettify(formatter="html"))
        now = datetime.now()
        log_date = now.strftime(constants.LOGS_DATETIME_FORMAT)
        url_str = str(url)
        response_url_str = str(response.url)
        clean_url = sanitize_filename(Path(url_str).as_posix().replace("/", "-"))
        filename = f"{clean_url[: self._max_html_stem_len]}_{log_date}.html"
        file_path = self._pages_folder / filename
        info = {
            "url": url_str,
            "response_url": response_url_str,
            "status_code": response.status,
            "datetime": now.isoformat(),
            "response_headers": dict(response.headers),
        }
        if exc:
            info |= {"error": str(exc), "exception": repr(exc)}

        json_data = json_dumps(info, indent=4, ensure_ascii=False)
        text = f"<!-- cyberdrop-dl scraping result\n{json_data}\n-->\n{content}"
        self.client_manager.manager.task_group.create_task(try_write(file_path, text))


async def try_write(file: Path, content: str) -> None:
    try:
        await asyncio.to_thread(file.write_text, content, "utf8")
    except OSError:
        pass
