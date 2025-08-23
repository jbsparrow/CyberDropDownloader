from __future__ import annotations

import asyncio
import contextlib
from contextlib import nullcontext
from datetime import datetime
from json import dumps as json_dumps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Self

import cyberdrop_dl.constants as constants
from cyberdrop_dl import env
from cyberdrop_dl.data_structures.url_objects import copy_signature
from cyberdrop_dl.exceptions import DDOSGuardError, DownloadError, InvalidContentTypeError, ScrapeError
from cyberdrop_dl.managers.client_manager import AbstractResponse
from cyberdrop_dl.utils.utilities import sanitize_filename

if TYPE_CHECKING:
    from aiohttp_client_cache.session import CachedSession
    from bs4 import BeautifulSoup
    from curl_cffi.requests.impersonate import BrowserTypeLiteral
    from curl_cffi.requests.models import Response as CurlResponse
    from curl_cffi.requests.session import HttpMethod

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
    from cyberdrop_dl.managers.client_manager import ClientManager


_curl_import_error = None
try:
    from curl_cffi.requests import AsyncSession  # noqa: TC002
except ImportError as e:
    _curl_import_error = e


_null_context = nullcontext()


def cache_control_manager(client_session: CachedSession, disabled: bool = False):
    if constants.DISABLE_CACHE or disabled:
        return client_session.disabled()
    return _null_context


class ScraperClient:
    """AIOHTTP / CURL operations for scraping."""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self._save_pages_html = client_manager.manager.config_manager.settings_data.files.save_pages_html
        self._pages_folder = self.client_manager.manager.path_manager.pages_folder
        min_html_file_path_len = len(str(self._pages_folder)) + len(constants.STARTUP_TIME_STR) + 10
        self._max_html_stem_len = 245 - min_html_file_path_len
        self._session: CachedSession
        self._curl_session: AsyncSession[CurlResponse]

    @contextlib.asynccontextmanager
    async def limiter(self, domain: str):
        with self.client_manager.request_context(domain):
            domain_limiter = self.client_manager.get_rate_limiter(domain)
            async with self.client_manager.global_rate_limiter, domain_limiter:
                await self.client_manager.manager.states.RUNNING.wait()
                yield

    def _startup(self) -> None:
        self._session = self.client_manager.new_scrape_session()
        self.reddit_session = self.client_manager.new_scrape_session()
        if _curl_import_error is not None:
            return

        self._curl_session = self.client_manager.new_curl_cffi_session()

    async def __aenter__(self) -> Self:
        self._startup()
        return self

    async def __aexit__(self, *args) -> None:
        await self._session.close()
        await self.reddit_session.close()
        if _curl_import_error is not None:
            return
        try:
            await self._curl_session.close()
        except Exception:
            pass

    def is_ddos(self, soup: BeautifulSoup) -> bool:
        return self.client_manager.check_ddos_guard(soup) or self.client_manager.check_cloudflare(soup)

    async def _request(
        self,
        url: AbsoluteHttpURL,
        method: HttpMethod = "GET",
        headers: dict[str, str] | None = None,
        impersonate: BrowserTypeLiteral | Literal[True] | None = None,
        data: Any = None,
        json: Any = None,
        cache_disabled: bool = False,
        **request_params: Any,
    ) -> AbstractResponse:
        request_params["headers"] = self.client_manager._headers | (headers or {})
        request_params["data"] = data
        request_params["json"] = json

        if impersonate:
            _check_curl_cffi_is_available()
            if impersonate is True:
                impersonate = "chrome"
            request_params["impersonate"] = impersonate
            response = await self._curl_session.request(method, str(url), **request_params)

        else:
            async with cache_control_manager(self._session, disabled=cache_disabled):
                response = await self._session._request(method, url, **request_params)

        abs_resp = AbstractResponse(response)
        exc = None
        try:
            await self.client_manager.check_http_status(response)
        except (DDOSGuardError, DownloadError) as e:
            exc = e
            raise

        else:
            if impersonate:
                self.client_manager.cookies.update_cookies(self._curl_session.cookies.get_dict(url.host), url)
            return abs_resp
        finally:
            self.client_manager.manager.task_group.create_task(self.write_soup_to_disk(url, abs_resp, exc))

    @copy_signature(_request)
    async def _request_json(self, *args, **kwargs) -> Any:
        return await (await self._request(*args, **kwargs)).json()

    @copy_signature(_request)
    async def _request_soup(self, *args, **kwargs) -> BeautifulSoup:
        return await (await self._request(*args, **kwargs)).soup()

    async def write_soup_to_disk(
        self,
        url: AbsoluteHttpURL,
        response: AbstractResponse,
        exc: Exception | None = None,
    ):
        """Writes html to a file."""
        if not self._save_pages_html:
            return

        content: str = ""
        try:
            content: str = (await response.soup()).prettify(formatter="html")
        except (UnicodeDecodeError, InvalidContentTypeError):
            pass

        content = content or await response.text()
        now = datetime.now()

        # The date is not really relevant in the filename and makes them longer, potencially truncating the URL part
        # But it garanties the filename will be unique
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
        try:
            await asyncio.to_thread(file_path.write_text, text, "utf8")
        except OSError:
            pass


def _check_curl_cffi_is_available() -> None:
    if _curl_import_error is None:
        return

    system = "Android" if env.RUNNING_IN_TERMUX else "the system"
    msg = (
        f"curl_cffi is required to scrape this URL but a dependency it's not available on {system}.\n"
        f"See: https://github.com/lexiforest/curl_cffi/issues/74#issuecomment-1849365636\n{_curl_import_error!r}"
    )
    raise ScrapeError("Missing Dependency", msg)
