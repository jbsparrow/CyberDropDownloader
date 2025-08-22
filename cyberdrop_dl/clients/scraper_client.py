from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from functools import wraps
from json import dumps as json_dumps
from json import loads as json_loads
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, Self, TypeVar, Unpack

import aiohttp
from aiohttp_client_cache.response import AnyResponse
from bs4 import BeautifulSoup

import cyberdrop_dl.constants as constants
from cyberdrop_dl import env
from cyberdrop_dl.exceptions import DDOSGuardError, DownloadError, InvalidContentTypeError, ScrapeError
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import get_soup_no_error, sanitize_filename

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from types import TracebackType

    from aiohttp_client_cache.session import CachedSession
    from curl_cffi.requests.impersonate import BrowserTypeLiteral as BrowserTarget
    from curl_cffi.requests.models import Response as CurlResponse
    from curl_cffi.requests.session import RequestParams as CurlRequestParams
    from multidict import CIMultiDictProxy

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
    from cyberdrop_dl.managers.client_manager import ClientManager

    HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY"]

_curl_import_error = None
try:
    from curl_cffi.requests import AsyncSession  # noqa: TC002
except ImportError as e:
    _curl_import_error = e

_P = ParamSpec("_P")
_R = TypeVar("_R")
_T = TypeVar("_T")


def limiter(func: Callable[_P, Coroutine[None, None, _R]]) -> Callable[_P, Coroutine[None, None, _R]]:
    """Wrapper to handle limits for scrape session."""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> _R:
        self: ScraperClient = args[0]
        domain: str = args[1]
        with self.client_manager.request_context(domain):
            domain_limiter = await self.client_manager.get_rate_limiter(domain)
            async with self.client_manager.session_limit, self.client_manager.global_rate_limiter, domain_limiter:
                await self.client_manager.manager.states.RUNNING.wait()
                if "cffi" in func.__name__:
                    _check_curl_cffi_is_available(domain)

                return await func(*args, **kwargs)

    return wrapper


def copy_signature(target: Callable[_P, _R]) -> Callable[[Callable[..., _T]], Callable[_P, _T]]:
    """Decorator to make a function mimic the signature of another function,
    but preserve the return type of the decorated function."""

    def decorator(func: Callable[..., _T]) -> Callable[_P, _T]:
        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            return func(*args, **kwargs)

        wrapper.__signature__ = inspect.signature(target).replace(  # type: ignore
            return_annotation=inspect.signature(func).return_annotation
        )
        return wrapper

    return decorator


@asynccontextmanager
async def cache_control_manager(client_session: CachedSession, disabled: bool = False):
    try:
        client_session.cache.disabled = constants.DISABLE_CACHE or disabled
        yield
    finally:
        client_session.cache.disabled = False


class ScraperClient:
    """AIOHTTP / CURL operations for scraping."""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self._save_pages_html = client_manager.manager.config_manager.settings_data.files.save_pages_html
        self._pages_folder = self.client_manager.manager.path_manager.pages_folder
        # folder len + date_prefix len + 10 [suffix (.html) + 1 OS separator + 4 (padding)]
        min_html_file_path_len = len(str(self._pages_folder)) + len(constants.STARTUP_TIME_STR) + 10
        self._max_html_stem_len = 245 - min_html_file_path_len
        self._session: CachedSession
        self._curl_session: AsyncSession[CurlResponse]

    def _startup(self) -> None:
        self._session = self.client_manager.new_scrape_session()
        self.reddit_session = self.client_manager.new_scrape_session()
        if _curl_import_error is not None:
            return

        self._curl_session = self.client_manager.new_curl_cffi_session()

    async def __aenter__(self) -> Self:
        self._startup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
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

    @asynccontextmanager
    async def write_soup_on_error(self, url, response: CurlResponse | aiohttp.ClientResponse):
        try:
            yield
        except (DDOSGuardError, DownloadError) as e:
            if self._save_pages_html and (soup := await get_soup_no_error(response)):
                await self.write_soup_to_disk(url, response, soup, exc=e)
            raise

    @limiter
    async def _request_cffi(
        self,
        domain: str,
        url: AbsoluteHttpURL,
        method: HttpMethod = "GET",
        **request_params: Unpack[CurlRequestParams],
    ) -> CurlResponse:
        headers: dict[str, Any] = request_params.get("headers") or {}  # type: ignore[reportAssignmentType]
        request_params["headers"] = self.client_manager._headers | headers
        response = await self._curl_session.request(method, str(url), **request_params)
        async with self.write_soup_on_error(url, response):
            await self.client_manager.check_http_status(response)
        self.client_manager.cookies.update_cookies(self._curl_session.cookies, url)
        return response

    @copy_signature(_request_cffi)
    async def request_json_cffi(self, *args, **kwargs) -> Any:
        response = await self._request_cffi(*args, **kwargs)
        return await response_to_json(response)

    async def _get_response_and_soup_cffi(
        self,
        domain: str,
        url: AbsoluteHttpURL,
        headers: dict[str, str] | None = None,
        impersonate: BrowserTarget | None = "chrome",
        request_params: dict[str, Any] | None = None,
    ) -> tuple[CurlResponse, BeautifulSoup]:
        """Makes a GET request using curl-cffi and creates a soup.

        :param domain: The crawler's domain (for rate limiting)
        :param url: The URL to fetch.
        :param headers: Optional headers to include in the request. Will be added to session's default headers.
        :param impersonate: Optional browser target to impersonate. Defaults to `chrome`.
        :param request_params: Additional keyword arguments to pass to `curl_session.get` (e.g., `timeout`).
        """
        request_params = request_params or {}
        response = await self._request_cffi(domain, url, headers=headers, impersonate=impersonate, **request_params)
        soup = await response_to_soup(response)
        if self._save_pages_html:
            await self.write_soup_to_disk(url, response, soup)
        return response, soup

    @copy_signature(_get_response_and_soup_cffi)
    async def get_soup_cffi(self, *args, **kwargs) -> BeautifulSoup:
        _, soup = await self._get_response_and_soup_cffi(*args, **kwargs)
        return soup

    @limiter
    async def post_data_cffi(
        self,
        domain: str,
        url: AbsoluteHttpURL,
        headers: dict[str, str] | None = None,
        impersonate: BrowserTarget | None = "chrome",
        data: Any = None,
        json: Any = None,
        request_params: dict[str, Any] | None = None,
    ) -> CurlResponse:
        """Makes a POST request using curl-cffi

        :param domain: The crawler's domain (for rate limiting)
        :param url: The URL to fetch.
        :param headers: Optional headers to include in the request. Will be added to session's default headers.
        :param impersonate: Optional browser target to impersonate. Defaults to `chrome`.
        :param data: Data to include in the requests. Will be sent as is (FormData).
        :param json: JSON data to include in the request. This will be serialized into a JSON string, and the `Content-Type` header will be set to `application/json`.
        :param request_params: Additional keyword arguments to pass to `curl_session.post` (e.g., `timeout`).
        """
        request_params = request_params or {}
        response = await self._request_cffi(
            domain,
            url,
            method="POST",
            data=data,
            json=json,
            impersonate=impersonate,
            headers=headers,
            **request_params,
        )
        return response

    # ~~~~~~~~~~~~~ AIOHTTP ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    async def _resilient_get(
        self, url: AbsoluteHttpURL, headers: dict[str, str], request_params: dict[str, Any] | None = None
    ) -> tuple[AnyResponse, BeautifulSoup | None]:
        """Makes a GET request and automatically retries it with flaresolverr (if needed)

        Only returns soup if flaresolverr was used"""
        request_params = request_params or {}
        for retry in range(2):
            response = await self._session.get(url, headers=headers, **request_params)
            async with self.write_soup_on_error(url, response):
                try:
                    await self.client_manager.check_http_status(response)
                except DDOSGuardError:
                    if retry == 0:
                        await self.client_manager.manager.cache_manager.request_cache.delete_url(url)
                        # TODO: Rebuilt response object from flaresolver response
                        soup, _ = await self.client_manager.flaresolverr.get(url, self._session)
                        if soup and not self.is_ddos(soup):
                            return response, soup
                        if self.client_manager.flaresolverr.enabled:
                            # retry again with the cookies we got from flaresolverr
                            continue
                    raise

                else:
                    return response, None

        return response, None

    @limiter
    async def _get(
        self,
        domain: str,
        url: AbsoluteHttpURL,
        /,
        headers: dict[str, str] | None = None,
        request_params: dict[str, Any] | None = None,
        *,
        cache_disabled: bool = False,
    ) -> tuple[AnyResponse, BeautifulSoup | None]:
        """_resilient_get with cache_control."""
        headers = self.client_manager._headers | (headers or {})
        async with cache_control_manager(self._session, disabled=cache_disabled):
            response, soup_or_none = await self._resilient_get(url, headers, request_params)

        return response, soup_or_none

    @copy_signature(_get)
    async def _get_response_and_soup(
        self, domain: str, url: AbsoluteHttpURL, *args, **kwargs
    ) -> tuple[AnyResponse, BeautifulSoup]:
        """
        Makes a GET request using aiohttp and creates a soup.

        :param domain: The crawler's domain (for rate limiting)
        :param url: The URL to fetch.
        :param headers:  Optional headers to include in the request. Will be added to session's default headers.
        :param request_params: Additional keyword arguments to pass to `session.get` (e.g., `timeout`).
        :param cache_disabled: Whether to disable caching for this request. Defaults to `False`.
        """

        response, soup_or_none = await self._get(domain, url, *args, **kwargs)

        if not soup_or_none:
            soup = await response_to_soup(response)
        else:
            soup: BeautifulSoup = soup_or_none

        if self._save_pages_html:
            await self.write_soup_to_disk(url, response, soup)
        return response, soup

    @copy_signature(_get_response_and_soup)
    async def get_soup(self, *args, **kwargs) -> BeautifulSoup:
        _, soup = await self._get_response_and_soup(*args, **kwargs)
        return soup

    @copy_signature(_get)
    async def get_json(self, *args, **kwargs) -> Any:
        response, soup_or_none = await self._get(*args, **kwargs)
        if soup_or_none:
            return json_loads(soup_or_none.text)
        return await response_to_json(response)

    @copy_signature(_get_response_and_soup)
    async def get_text(self, *args, **kwargs) -> str:
        response, soup_or_none = await self._get(*args, **kwargs)
        if soup_or_none:
            return soup_or_none.text
        return await response.text()

    @limiter
    async def _post_data(
        self,
        domain: str,
        url: AbsoluteHttpURL,
        headers: dict[str, str] | None = None,
        data: Any = None,
        json: Any = None,
        request_params: dict[str, Any] | None = None,
        *,
        cache_disabled: bool = False,
    ) -> aiohttp.ClientResponse:
        """Makes a post request using aiohtttp

        :param domain: The crawler's domain (for rate limiting)
        :param url: The URL to fetch.
        :param headers: Optional headers to include in the request. Will be added to session's default headers.
        :param data: Data to include in the requests. Will be sent as is (FormData).
        :param json: JSON data to include in the request. This will be serialized into a JSON string, and the `Content-Type` header will be set to `application/json`.
        :param request_params: Additional keyword arguments to pass to `session.post` (e.g., `timeout`).
        :param cache_disabled: Whether to disable caching for this request. Defaults to `False`.
        """
        request_params = request_params or {}
        headers = self.client_manager._headers | {"Accept-Encoding": "identity"} | (headers or {})
        async with cache_control_manager(self._session, disabled=cache_disabled):
            response = await self._session.post(url, headers=headers, data=data, json=json, **request_params)
        await self.client_manager.check_http_status(response)
        return response

    @copy_signature(_post_data)
    async def post_data_raw(self, *args: Any, **kwargs: Any) -> bytes:
        response = await self._post_data(*args, **kwargs)
        if response.status == 204:
            raise ScrapeError(204)
        return await response.read()

    @copy_signature(_post_data)
    async def post_data(self, *args: Any, **kwargs: Any) -> Any:
        content = await self.post_data_raw(*args, **kwargs)
        return json_loads(content)

    @copy_signature(_post_data)
    async def post_data_get_soup(self, *args: Any, **kwargs: Any) -> BeautifulSoup:
        content = await self.post_data_raw(*args, **kwargs)
        return BeautifulSoup(content, "html.parser")

    @limiter
    async def _get_head(
        self,
        domain: str,
        url: AbsoluteHttpURL,
        headers: dict[str, str] | None = None,
        request_params: dict[str, Any] | None = None,
        *,
        cache_disabled: bool = False,
    ) -> aiohttp.ClientResponse:
        """
        Makes a GET request to an URL and returns its headers

        :param domain: The crawler's domain (for rate limiting)
        :param url: The URL to fetch.
        :param headers:  Optional headers to include in the request. Will be added to session's default headers.
        :param request_params: Additional keyword arguments to pass to `session.head` (e.g., `timeout`).
        :param cache_disabled: Whether to disable caching for this request. Defaults to `False`.
        """
        request_params = request_params or {}
        headers = self.client_manager._headers | {"Accept-Encoding": "identity"} | (headers or {})
        async with cache_control_manager(self._session, disabled=cache_disabled):
            response = await self._session.head(url, headers=headers, **request_params)
        await self.client_manager.check_http_status(response)
        return response

    @copy_signature(_get_head)
    async def get_head(self, *args: Any, **kwargs: Any) -> CIMultiDictProxy[str]:
        response = await self._get_head(*args, **kwargs)
        return response.headers

    async def write_soup_to_disk(
        self,
        url: AbsoluteHttpURL,
        response: CurlResponse | AnyResponse,
        soup: BeautifulSoup,
        exc: Exception | None = None,
    ):
        """Writes html to a file."""
        html_text: str = soup.prettify(formatter="html")  # type: ignore # Not sure if we should prettify
        status_code: int = response.status_code if hasattr(response, "status_code") else response.status  # type: ignore
        response_headers = dict(response.headers)
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
            "status_code": status_code,
            "datetime": now.isoformat(),
            "response_headers": response_headers,
        }
        if exc:
            info = info | {"error": str(exc), "exception": repr(exc)}

        json_data = json_dumps(info, indent=4, ensure_ascii=False)
        text = f"<!-- cyberdrop-dl scraping result\n{json_data}\n-->\n{html_text}"
        try:
            await asyncio.to_thread(file_path.write_text, text, "utf8")
        except OSError:
            pass


async def response_to_soup(response: AnyResponse | CurlResponse) -> BeautifulSoup:
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text" in content_type or "html" in content_type:
        if isinstance(response, AnyResponse):
            content = await response.text()
        else:
            content = response.text

        return BeautifulSoup(content, "html.parser")

    raise InvalidContentTypeError(message=f"Received {content_type}, was expecting text")


async def response_to_json(response: AnyResponse | CurlResponse) -> Any:
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/plain" in content_type or "json" in content_type:
        if isinstance(response, AnyResponse):
            content = await response.text()
        else:
            content = response.text
        return json_loads(content)

    raise InvalidContentTypeError(message=f"Received {content_type}, was expecting JSON")


def add_request_log_hooks(trace_configs: list[aiohttp.TraceConfig]) -> None:
    async def on_request_start(*args):
        params: aiohttp.TraceRequestStartParams = args[2]
        log_debug(f"Starting scrape {params.method} request to {params.url}", 10)

    async def on_request_end(*args):
        params: aiohttp.TraceRequestEndParams = args[2]
        msg = f"Finishing scrape {params.method} request to {params.url}"
        msg += f" -> response status: {params.response.status}"
        log_debug(msg, 10)

    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)
    trace_configs.append(trace_config)


def _check_curl_cffi_is_available(domain: str) -> None:
    if _curl_import_error is not None:
        system = "Android" if env.RUNNING_IN_TERMUX else "the system"
        msg = f"curl_cffi is required to scrape URLs from {domain}, but a dependency it's not available on {system}.\n"
        msg += f"See: https://github.com/lexiforest/curl_cffi/issues/74#issuecomment-1849365636\n{_curl_import_error!r}"
        raise ScrapeError("Missing Dependency", msg)
