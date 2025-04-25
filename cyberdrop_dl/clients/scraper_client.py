from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import field
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import aiohttp
from aiohttp_client_cache import CachedSession
from aiohttp_client_cache.response import CachedStreamReader
from bs4 import BeautifulSoup

import cyberdrop_dl.utils.constants as constants
from cyberdrop_dl import env
from cyberdrop_dl.clients.errors import DDOSGuardError, DownloadError, InvalidContentTypeError, ScrapeError
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import get_soup_from_response, sanitize_filename

curl_import_error = None
try:
    from curl_cffi.requests import AsyncSession
except ImportError as e:
    curl_import_error = e

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from curl_cffi.requests.impersonate import BrowserTypeLiteral
    from curl_cffi.requests.models import Response as CurlResponse
    from multidict import CIMultiDictProxy
    from yarl import URL

    from cyberdrop_dl.managers.client_manager import ClientManager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


P = ParamSpec("P")
R = TypeVar("R")


def limiter(func: Callable[P, Coroutine[None, None, R]]) -> Callable[P, Coroutine[None, None, R]]:
    """Wrapper handles limits for scrape session."""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> R:
        self: ScraperClient = args[0]
        domain: str = args[1]
        domain_limiter = await self.client_manager.get_rate_limiter(domain)
        async with self.client_manager.session_limit:
            await self._global_limiter.acquire()
            await domain_limiter.acquire()
            await self.client_manager.manager.states.RUNNING.wait()

            if "cffi" in func.__name__:
                if curl_import_error is not None:
                    system = "Android" if env.RUNNING_IN_TERMUX else "the system"
                    msg = f"curl_cffi is required to scrape URLs from {domain}, but a dependency it's not available on {system}.\n"
                    msg += f"See: https://github.com/lexiforest/curl_cffi/issues/74#issuecomment-1849365636\n{curl_import_error!r}"
                    raise ScrapeError("Missing Dependency", msg)
                kwargs.pop("client_session", None)
                return await func(*args, **kwargs)

            kwargs["client_session"] = self._session
            return await func(*args, **kwargs)

    return wrapper


@asynccontextmanager
async def cache_control_manager(client_session: CachedSession, disabled: bool = False):
    client_session.cache.disabled = constants.DISABLE_CACHE or disabled
    yield
    client_session.cache.disabled = False


class ScraperClient:
    """AIOHTTP operations for scraping."""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self._headers = {"user-agent": client_manager.user_agent}
        self._timeout_tuple = client_manager.connection_timeout + 60, client_manager.connection_timeout
        self._timeouts = aiohttp.ClientTimeout(*self._timeout_tuple)
        self._global_limiter = self.client_manager.global_rate_limiter
        self.trace_configs = []
        self.save_pages_html = client_manager.manager.config_manager.settings_data.files.save_pages_html
        self.pages_folder = self.client_manager.manager.path_manager.pages_folder
        # folder len + date_prefix len + 10 [suffix (.html) + 1 OS separator + 4 (padding)]
        min_html_file_path_len = len(str(self.pages_folder)) + len(constants.STARTUP_TIME_STR) + 10
        self.max_html_stem_len = 245 - min_html_file_path_len
        self._session: CachedSession = field(init=False)

    def startup(self):
        self.add_request_log_hooks()
        self._session = CachedSession(
            headers=self._headers,
            raise_for_status=False,
            cookie_jar=self.client_manager.cookies,
            timeout=self._timeouts,
            trace_configs=self.trace_configs,
            cache=self.client_manager.manager.cache_manager.request_cache,
        )

    async def close(self):
        await self._session.close()

    @asynccontextmanager
    async def write_soup_on_error(self, domain: str, url, response: CurlResponse | aiohttp.ClientResponse):
        try:
            yield
        except (DDOSGuardError, DownloadError) as e:
            if self.save_pages_html and (soup := await get_soup_from_response(response)):
                await self.write_soup_to_disk(domain, url, response, soup, exc=e)
            raise

    @asynccontextmanager
    async def new_curl_session(self, impersonate):
        proxy = str(self.client_manager.proxy) if self.client_manager.proxy else None
        async with AsyncSession(
            headers=self._headers,
            impersonate=impersonate,
            verify=bool(self.client_manager.ssl_context),
            proxy=proxy,
            timeout=self._timeout_tuple,
            cookies={c.key: c.value for c in self.client_manager.cookies},
        ) as curl_session:
            yield curl_session

    def add_request_log_hooks(self) -> None:
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
        self.trace_configs.append(trace_config)

    @limiter
    async def get_soup_cffi(
        self, domain: str, url: URL, impersonate: BrowserTypeLiteral | None = "chrome", **_
    ) -> BeautifulSoup:
        async with self.new_curl_session(impersonate) as session:
            response: CurlResponse = await session.get(str(url))
            async with self.write_soup_on_error(domain, url, response):
                await self.client_manager.check_http_status(response)
                content_type: str = response.headers.get("Content-Type")
                assert content_type is not None
                if not any(s in content_type.lower() for s in ("html", "text")):
                    raise InvalidContentTypeError(message=f"Received {content_type}, was expecting text")
                self.client_manager.cookies.update_cookies(session.cookies, url)
                soup = BeautifulSoup(response.content, "html.parser")
                if self.save_pages_html:
                    await self.write_soup_to_disk(domain, url, response, soup)
                return soup

    @limiter
    async def post_data_cffi(
        self,
        domain: str,
        url: URL,
        impersonate: BrowserTypeLiteral | None = "chrome",
        data: dict | None = None,
        **kwargs: Any,
    ) -> CurlResponse:
        """**kwargs are passed to `session.post`"""
        data = data or {}
        async with self.new_curl_session(impersonate) as session:
            response: CurlResponse = await session.post(str(url), data=data, **kwargs)
            await self.client_manager.check_http_status(response)
            return response

    @limiter
    async def get_soup(
        self,
        domain: str,
        url: URL,
        client_session: CachedSession,
        origin: ScrapeItem | URL | None = None,
        with_response_url: bool = False,
        cache_disabled: bool = False,
        retry: bool = True,
        *,
        with_response_headers: bool = False,
    ) -> BeautifulSoup | tuple[BeautifulSoup, CIMultiDictProxy | URL]:
        """Returns a BeautifulSoup object from the given URL."""
        async with (
            cache_control_manager(client_session, disabled=cache_disabled),
            client_session.get(
                url, headers=self._headers, ssl=self.client_manager.ssl_context, proxy=self.client_manager.proxy
            ) as response,
            self.write_soup_on_error(domain, url, response),
        ):
            try:
                await self.client_manager.check_http_status(response, origin=origin)
            except DDOSGuardError:
                await self.client_manager.manager.cache_manager.request_cache.delete_url(url)
                soup, response_URL = await self.client_manager.flaresolverr.get(
                    url,
                    client_session,
                    origin,
                )
                # retry request with flaresolverr cookies
                if not soup or (
                    self.client_manager.check_ddos_guard(soup) or self.client_manager.check_cloudflare(soup)
                ):
                    if not retry:
                        raise DDOSGuardError(message="Unable to access website with flaresolverr cookies") from None
                    return await self.get_soup(
                        domain,
                        url,
                        origin=origin,
                        with_response_url=with_response_url,
                        retry=False,
                        cache_disabled=True,
                    )
                if with_response_url:
                    return soup, response_URL
                if with_response_headers:
                    return soup, response.headers
                return soup

            content_type = response.headers.get("Content-Type")
            assert content_type is not None
            if not any(s in content_type.lower() for s in ("html", "text")):
                raise InvalidContentTypeError(message=f"Received {content_type}, was expecting text", origin=origin)
            text = await CachedStreamReader(await response.read()).read()
            soup = BeautifulSoup(text, "html.parser")
            if self.save_pages_html:
                await self.write_soup_to_disk(domain, url, response, soup)
            if with_response_url:
                return soup, response.url
            return soup

    async def get_soup_and_return_url(
        self, domain: str, url: URL, origin: ScrapeItem | URL | None = None, **kwargs
    ) -> tuple[BeautifulSoup, URL]:
        """Returns a BeautifulSoup object and response URL from the given URL."""
        return await self.get_soup(domain, url, origin=origin, with_response_url=True, **kwargs)

    @limiter
    async def get_json(
        self,
        domain: str,
        url: URL,
        params: dict | None = None,
        headers_inc: dict | None = None,
        client_session: CachedSession = None,  # type: ignore
        origin: ScrapeItem | URL | None = None,
        cache_disabled: bool = False,
    ) -> dict:
        """Returns a JSON object from the given URL."""
        headers = self._headers | headers_inc if headers_inc else self._headers
        async with (
            cache_control_manager(client_session, disabled=cache_disabled),
            client_session.get(
                url,
                headers=headers,
                ssl=self.client_manager.ssl_context,
                proxy=self.client_manager.proxy,
                params=params,
            ) as response,
        ):
            await self.client_manager.check_http_status(response, origin=origin)
            content_type = response.headers.get("Content-Type")
            assert content_type is not None
            if "json" not in content_type.lower():
                raise InvalidContentTypeError(message=f"Received {content_type}, was expecting JSON", origin=origin)
            json_resp = await response.json()
            if cache_disabled:
                return json_resp, response  # type: ignore
            return json_resp

    @limiter
    async def get_text(
        self,
        domain: str,
        url: URL,
        client_session: CachedSession,
        origin: ScrapeItem | URL | None = None,
        cache_disabled: bool = False,
        retry: bool = True,
    ) -> str:
        """Returns a text object from the given URL."""
        async with (
            cache_control_manager(client_session, disabled=cache_disabled),
            client_session.get(
                url, headers=self._headers, ssl=self.client_manager.ssl_context, proxy=self.client_manager.proxy
            ) as response,
        ):
            try:
                await self.client_manager.check_http_status(response, origin=origin)
            except DDOSGuardError:
                await self.client_manager.manager.cache_manager.request_cache.delete_url(url)
                soup, _ = await self.client_manager.flaresolverr.get(url, client_session, origin)
                if not soup or (
                    self.client_manager.check_ddos_guard(soup) or self.client_manager.check_cloudflare(soup)
                ):
                    if not retry:
                        raise DDOSGuardError(message="Unable to access website with flaresolverr cookies") from None
                    return await self.get_text(domain, url, origin=origin, retry=False, cache_disabled=True)
                return str(soup)
            return await response.text()

    @limiter
    async def post_data(
        self,
        domain: str,
        url: URL,
        client_session: CachedSession,
        data: dict,
        req_resp: bool = True,
        raw: bool = False,
        origin: ScrapeItem | URL | None = None,
        cache_disabled: bool = False,
        headers_inc: dict | None = None,
        *,
        req_headers: bool = False,
    ) -> dict | bytes:
        """Returns a JSON object from the given URL when posting data. If raw == True, returns raw binary data of response."""
        headers = self._headers | headers_inc if headers_inc else self._headers
        async with (
            cache_control_manager(client_session, disabled=cache_disabled),
            client_session.post(
                url,
                headers=headers,
                ssl=self.client_manager.ssl_context,
                proxy=self.client_manager.proxy,
                data=data,
                allow_redirects=req_headers,
            ) as response,
        ):
            await self.client_manager.check_http_status(response, origin=origin)
            if req_resp:
                if response.status == 204:
                    raise ScrapeError(204)
                content = await response.content.read()
                if content == b"":
                    content = await CachedStreamReader(await response.read()).read()
                return content if raw else json.loads(content)
            if req_headers:
                return dict(response.headers)
            return {}

    @limiter
    async def get_head(
        self, domain: str, url: URL, client_session: CachedSession, *, origin: ScrapeItem | URL | None = None
    ) -> CIMultiDictProxy[str]:
        """Returns the headers from the given URL."""
        async with client_session.head(
            url,
            headers=self._headers | {"Accept-Encoding": "identity"},
            ssl=self.client_manager.ssl_context,
            proxy=self.client_manager.proxy,
        ) as response:
            await self.client_manager.check_http_status(response, origin=origin)
            return response.headers

    async def write_soup_to_disk(
        self,
        domain: str,
        url: URL,
        response: CurlResponse | aiohttp.ClientResponse,
        soup: BeautifulSoup,
        exc: Exception | None = None,
    ):
        html_text: str = soup.prettify(formatter="html")  # Not sure if we should prettify
        status_code: int = response.status_code if hasattr(response, "status_code") else response.status  # type: ignore
        response_headers = dict(response.headers)
        now = datetime.now()

        # The date is not really relevant in the filename and makes them longer, potencially truncating the URL part
        # But it garanties the filename will be unique
        log_date = now.strftime(constants.LOGS_DATETIME_FORMAT)
        url_str = str(url)
        response_url_str = str(response.url)
        clean_url = sanitize_filename(Path(url_str).as_posix().replace("/", "-"))
        filename = f"{clean_url[: self.max_html_stem_len]}_{log_date}.html"
        file_path = self.pages_folder / filename
        info = {
            "crawler": domain,
            "url": url_str,
            "response_url": response_url_str,
            "status_code": status_code,
            "datetime": now.isoformat(),
            "response_headers": response_headers,
        }
        if exc:
            info = info | {"error": str(exc), "exception": repr(exc)}
        text = f"<!-- cyberdrop-dl scraping result\n{json.dumps(info, indent=4, ensure_ascii=False)}\n-->\n{html_text}"
        try:
            await asyncio.to_thread(file_path.write_text, text, "utf8")
        except OSError:
            pass
