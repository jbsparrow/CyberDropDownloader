from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import field
from datetime import datetime
from functools import wraps
from json import dumps as json_dumps
from json import loads as json_loads
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import aiohttp
from aiohttp_client_cache import CachedSession
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

    from aiohttp_client_cache.response import AnyResponse
    from curl_cffi.requests.impersonate import BrowserTypeLiteral as BrowserTarget
    from curl_cffi.requests.models import Response as CurlResponse
    from multidict import CIMultiDictProxy
    from yarl import URL

    from cyberdrop_dl.managers.client_manager import ClientManager


P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


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
                return await func(*args, **kwargs)

            return await func(*args, **kwargs)

    return wrapper


def copy_signature(target: Callable[P, R]) -> Callable[[Callable[..., T]], Callable[P, T]]:
    """
    Decorator to make a function mimic the signature of another function,
    but preserve the return type of the decorated function.
    """

    def decorator(func: Callable[..., T]) -> Callable[P, T]:
        """The actual decorator."""

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            """The wrapper function."""
            return func(*args, **kwargs)

        wrapper.__signature__ = inspect.signature(target).replace(  # type: ignore
            return_annotation=inspect.signature(func).return_annotation
        )
        return wrapper

    return decorator


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
        self._curl_session: AsyncSession = field(init=False)

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
        proxy = str(self.client_manager.proxy) if self.client_manager.proxy else None
        self._curl_session = AsyncSession(
            headers=self._headers,
            impersonate="chrome",
            verify=bool(self.client_manager.ssl_context),
            proxy=proxy,
            timeout=self._timeout_tuple,
            cookies={c.key: c.value for c in self.client_manager.cookies},
        )

    async def close(self):
        await self._session.close()
        await self._curl_session.close()

    def is_ddos(self, soup: BeautifulSoup) -> bool:
        return self.client_manager.check_ddos_guard(soup) or self.client_manager.check_cloudflare(soup)

    @asynccontextmanager
    async def write_soup_on_error(self, url, response: CurlResponse | aiohttp.ClientResponse):
        try:
            yield
        except (DDOSGuardError, DownloadError) as e:
            if self.save_pages_html and (soup := await get_soup_from_response(response)):
                await self.write_soup_to_disk(url, response, soup, exc=e)
            raise

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
        self,
        domain: str,
        url: URL,
        headers: dict[str, str] | None = None,
        impersonate: BrowserTarget | None = "chrome",
        **kwargs: Any,
    ) -> BeautifulSoup:
        headers = self._headers | (headers or {})
        response: CurlResponse = await self._curl_session.get(
            str(url), impersonate=impersonate, headers=headers, **kwargs
        )
        async with self.write_soup_on_error(url, response):
            await self.client_manager.check_http_status(response)
            content_type: str = response.headers.get("Content-Type")
            assert content_type is not None
            if not any(s in content_type.lower() for s in ("html", "text")):
                raise InvalidContentTypeError(message=f"Received {content_type}, was expecting text")
            self.client_manager.cookies.update_cookies(self._curl_session.cookies, url)
            soup = BeautifulSoup(response.content, "html.parser")
            if self.save_pages_html:
                await self.write_soup_to_disk(url, response, soup)
            return soup

    @limiter
    async def post_data_cffi(
        self,
        domain: str,
        url: URL,
        headers: dict[str, str] | None = None,
        impersonate: BrowserTarget | None = "chrome",
        data: dict | None = None,
        json: dict | None = None,
        **kwargs: Any,
    ) -> CurlResponse:
        """**kwargs are passed to `session.post`"""
        headers = self._headers | (headers or {})
        response: CurlResponse = await self._curl_session.post(
            str(url), data=data, json=json, impersonate=impersonate, headers=headers, **kwargs
        )
        await self.client_manager.check_http_status(response)
        return response

    # ~~~~~~~~~~~~~ AIOHTTP ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    async def _resiliant_get(self, url: URL, **request_params: Any) -> tuple[AnyResponse, BeautifulSoup | None]:
        """Makes a get requests an atomatically retryes with flaresolverr if needed"""
        for retry in range(2):
            response = await self._session.get(url, **request_params)
            async with self.write_soup_on_error(url, response):
                try:
                    await self.client_manager.check_http_status(response)
                except DDOSGuardError:
                    await self.client_manager.manager.cache_manager.request_cache.delete_url(url)
                    soup, _ = await self.client_manager.flaresolverr.get(url, self._session)
                    if not soup or self.is_ddos(soup):
                        if retry == 0:
                            # retry again with the cookies we got from flaresolverr
                            continue
                        raise
                    return response, soup

                else:
                    return response, await response_to_soup(response)

        return response, None

    @limiter
    async def _get_response_and_soup(
        self, domain: str, url: URL, headers: dict[str, str] | None = None, cache_disabled: bool = False
    ) -> tuple[AnyResponse, BeautifulSoup]:
        """Returns a BeautifulSoup object from the given URL."""
        headers = self._headers | (headers or {})
        async with cache_control_manager(self._session, disabled=cache_disabled):
            response, soup_or_none = await self._resiliant_get(url, headers=headers)
            if not soup_or_none:
                soup = await response_to_soup(response)
            else:
                soup: BeautifulSoup = soup_or_none

            if self.save_pages_html:
                await self.write_soup_to_disk(url, response, soup)
            return response, soup

    @copy_signature(_get_response_and_soup)
    async def get_soup(self, *args, **kwargs) -> BeautifulSoup:
        """Returns a BeautifulSoup object from the given URL."""
        _, soup = await self._get_response_and_soup(*args, **kwargs)
        return soup

    @copy_signature(_get_response_and_soup)
    async def get_json(self, *args, **kwargs) -> dict[str, Any]:
        """Returns a JSON object from the given URL."""
        response, _ = await self._get_response_and_soup(*args, **kwargs)
        return await response_to_json(response)

    @copy_signature(_get_response_and_soup)
    async def get_text(self, *args, **kwargs) -> str:
        response, soup = await self._get_response_and_soup(*args, **kwargs)
        if soup:
            return soup.text
        else:
            return await response.text()

    @limiter
    async def _post_data(
        self,
        domain: str,
        url: URL,
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        *,
        cache_disabled: bool = False,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Returns a JSON object from the given URL when posting data. If raw == True, returns raw binary data of response."""
        headers = self._headers | {"Accept-Encoding": "identity"} | (headers or {})
        async with cache_control_manager(self._session, disabled=cache_disabled):
            response = await self._session.post(url, headers=headers, data=data, json=json, **kwargs)
            await self.client_manager.check_http_status(response)
            return response

    @copy_signature(_post_data)
    async def post_data_raw(self, *args: Any, **kwargs: Any) -> bytes:
        """Hola"""
        response = await self._post_data(*args, **kwargs)
        if response.status == 204:
            raise ScrapeError(204)
        return await response.read()

    @copy_signature(post_data_raw)
    async def post_data(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Hola2"""
        content = await self.post_data_raw(*args, **kwargs)
        return json_loads(content)

    @limiter
    async def get_head(self, domain: str, url: URL, headers: dict | None = None) -> CIMultiDictProxy[str]:
        """Returns the headers from the given URL."""
        headers = self._headers | {"Accept-Encoding": "identity"} | (headers or {})
        response = await self._session.head(url, headers=headers)
        await self.client_manager.check_http_status(response)
        return response.headers

    async def write_soup_to_disk(
        self,
        url: URL,
        response: CurlResponse | AnyResponse,
        soup: BeautifulSoup,
        exc: Exception | None = None,
    ):
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
        filename = f"{clean_url[: self.max_html_stem_len]}_{log_date}.html"
        file_path = self.pages_folder / filename
        info = {
            "url": url_str,
            "response_url": response_url_str,
            "status_code": status_code,
            "datetime": now.isoformat(),
            "response_headers": response_headers,
        }
        if exc:
            info = info | {"error": str(exc), "exception": repr(exc)}
        text = f"<!-- cyberdrop-dl scraping result\n{json_dumps(info, indent=4, ensure_ascii=False)}\n-->\n{html_text}"
        try:
            await asyncio.to_thread(file_path.write_text, text, "utf8")
        except OSError:
            pass


async def response_to_soup(response: AnyResponse) -> BeautifulSoup:
    content_type: str = response.headers["Content-Type"]
    if not any(s in content_type.lower() for s in ("html", "text")):
        raise InvalidContentTypeError(message=f"Received {content_type}, was expecting text")
    text = await response.read()
    return BeautifulSoup(text, "html.parser")


async def response_to_json(response: AnyResponse) -> dict[str, Any]:
    content_type: str = response.headers["Content-Type"].lower()
    if "text/plain" in content_type:
        return json_loads(await response.text())
    elif "json" in content_type:
        return await response.json() or {}
    else:
        raise InvalidContentTypeError(message=f"Received {content_type}, was expecting JSON")
