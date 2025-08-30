from __future__ import annotations

import asyncio
import contextlib
import ssl
from collections import defaultdict
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Literal, overload

import aiohttp
import certifi
import truststore
from aiohttp import ClientResponse, ClientSession, ContentTypeError
from aiohttp_client_cache.session import CachedSession
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup

from cyberdrop_dl import constants, env
from cyberdrop_dl.clients.download_client import DownloadClient
from cyberdrop_dl.clients.scraper_client import ScraperClient
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DDOSGuardError, DownloadError, ScrapeError, TooManyCrawlerErrors
from cyberdrop_dl.managers.download_speed_manager import DownloadSpeedLimiter
from cyberdrop_dl.ui.prompts.user_prompts import get_cookies_from_browsers
from cyberdrop_dl.utils.cookie_management import read_netscape_files
from cyberdrop_dl.utils.logger import log, log_debug, log_spacer
from cyberdrop_dl.utils.utilities import get_soup_no_error

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Mapping
    from http.cookies import BaseCookie

    from aiohttp_client_cache.response import CachedResponse
    from curl_cffi.requests import AsyncSession
    from curl_cffi.requests.models import Response as CurlResponse

    from cyberdrop_dl.managers.manager import Manager

DOWNLOAD_ERROR_ETAGS = {
    "d835884373f4d6c8f24742ceabe74946": "Imgur image has been removed",
    "65b7753c-528a": "SC Scrape Image",
    "5c4fb843-ece": "PixHost Removed Image",
    "637be5da-11d2b": "eFukt Video removed",
    "63a05f27-11d2b": "eFukt Video removed",
    "5a56b09d-1485eb": "eFukt Video removed",
}

_crawler_errors: dict[str, int] = defaultdict(int)


class DDosGuard:
    TITLES = ("Just a moment...", "DDoS-Guard")
    SELECTORS = (
        "#cf-challenge-running",
        ".ray_id",
        ".attack-box",
        "#cf-please-wait",
        "#challenge-spinner",
        "#trk_jschal_js",
        "#turnstile-wrapper",
        ".lds-ring",
    )
    ALL_SELECTORS = ", ".join(SELECTORS)


class CloudflareTurnstile:
    TITLES = ("Simpcity Cuck Detection", "Attention Required! | Cloudflare", "Sentinel CAPTCHA")
    SELECTORS = (
        "captchawrapper",
        "cf-turnstile",
        "script[src*='challenges.cloudflare.com/turnstile']",
        "script:contains('Dont open Developer Tools')",
    )
    ALL_SELECTORS = ", ".join(SELECTORS)


class ClientManager:
    """Creates a 'client' that can be referenced by scraping or download sessions."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        ssl_context = self.manager.global_config.general.ssl_context
        if not ssl_context:
            self.ssl_context = False
        elif ssl_context == "certifi":
            self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        elif ssl_context == "truststore":
            self.ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        elif ssl_context == "truststore+certifi":
            self.ssl_context = ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.load_verify_locations(cafile=certifi.where())

        self.cookies = aiohttp.CookieJar(quote_cookie=False)
        self.domain_rate_limits = {
            "bunkrr": AsyncLimiter(5, 1),
            "cyberdrop": AsyncLimiter(5, 1),
            "coomer": AsyncLimiter(1, 1),
            "kemono": AsyncLimiter(1, 1),
            "pixeldrain": AsyncLimiter(10, 1),
            "gofile": AsyncLimiter(100, 60),
            "hitomi.la": AsyncLimiter(3, 1),
            "other": AsyncLimiter(25, 1),
        }

        self.download_spacer = {
            "bunkr": 0.5,
            "bunkrr": 0.5,
            "cyberdrop": 0,
            "cyberfile": 0,
            "pixeldrain": 0,
            "coomer": 0.5,
            "kemono": 0.5,
            "nhentai.net": 1,
        }

        self.global_rate_limiter = AsyncLimiter(self.manager.global_config.rate_limiting_options.rate_limit, 1)
        self.session_limit = asyncio.Semaphore(50)
        self.download_session_limit = asyncio.Semaphore(
            self.manager.global_config.rate_limiting_options.max_simultaneous_downloads
        )

        self.scraper_session = ScraperClient(self)
        self.speed_limiter = DownloadSpeedLimiter(manager)
        self.downloader_session = DownloadClient(manager, self)
        self.flaresolverr = Flaresolverr(self)
        self._headers = {"user-agent": self.manager.global_config.general.user_agent}

    def filter_cookies_by_word_in_domain(self, word: str) -> Iterable[tuple[str, BaseCookie[str]]]:
        """Yields pairs of `[domain, BaseCookie]` for every cookie with a domain that has `word` in it"""
        if not self.cookies:
            return
        self.cookies._do_expiration()
        for domain, _ in self.cookies._cookies:
            if word in domain:
                yield domain, self.cookies.filter_cookies(AbsoluteHttpURL(f"https://{domain}"))

    async def startup(self) -> None:
        await _set_dns_resolver()

    def new_curl_cffi_session(self) -> AsyncSession:
        # Calling code should have validated if curl is actually available
        from curl_cffi.requests import AsyncSession

        proxy_or_none = str(proxy) if (proxy := self.manager.global_config.general.proxy) else None
        return AsyncSession(
            headers=self._headers,
            impersonate="chrome",
            verify=bool(self.ssl_context),
            proxy=proxy_or_none,
            timeout=self.manager.global_config.rate_limiting_options._timeout,
            cookies={cookie.key: cookie.value for cookie in self.cookies},
        )

    def new_scrape_session(self) -> CachedSession:
        trace_configs = _create_request_log_hooks("scrape")
        return self._new_session(cached=True, trace_configs=trace_configs)

    def new_download_session(self) -> ClientSession:
        trace_configs = _create_request_log_hooks("download")
        return self._new_session(cached=False, trace_configs=trace_configs)

    @overload
    def _new_session(
        self, cached: Literal[True], trace_configs: list[aiohttp.TraceConfig] | None = None
    ) -> CachedSession: ...

    @overload
    def _new_session(
        self, cached: Literal[False] = False, trace_configs: list[aiohttp.TraceConfig] | None = None
    ) -> ClientSession: ...

    def _new_session(
        self, cached: bool = False, trace_configs: list[aiohttp.TraceConfig] | None = None
    ) -> CachedSession | ClientSession:
        if cached:
            timeout = self.manager.global_config.rate_limiting_options._scrape_timeout
            session_cls = CachedSession
            kwargs: dict[str, Any] = {"cache": self.manager.cache_manager.request_cache}
        else:
            timeout = self.manager.global_config.rate_limiting_options._download_timeout
            session_cls = ClientSession
            kwargs = {}
        return session_cls(
            headers=self._headers,
            raise_for_status=False,
            cookie_jar=self.cookies,
            timeout=timeout,
            trace_configs=trace_configs,
            proxy=self.manager.global_config.general.proxy,
            connector=self._new_tcp_connector(),
            **kwargs,
        )

    def _new_tcp_connector(self) -> aiohttp.TCPConnector:
        assert constants.DNS_RESOLVER is not None
        conn = aiohttp.TCPConnector(ssl=self.ssl_context, resolver=constants.DNS_RESOLVER())
        conn._resolver_owner = True
        return conn

    def check_domain_errors(self, domain: str) -> None:
        if _crawler_errors[domain] >= env.MAX_CRAWLER_ERRORS:
            if crawler := self.manager.scrape_mapper.disable_crawler(domain):
                msg = (
                    f"{crawler.__class__.__name__} has been disabled after too many errors. "
                    f"URLs from the following domains will be ignored: {crawler.SCRAPE_MAPPER_KEYS}"
                )
                log(msg, 40)
            raise TooManyCrawlerErrors

    @contextlib.contextmanager
    def request_context(self, domain: str) -> Generator[None]:
        self.check_domain_errors(domain)
        try:
            yield
        except DDOSGuardError:
            _crawler_errors[domain] += 1
            raise
        else:
            # we could potencially reset the counter here
            # _crawler_errors[domain] = 0
            pass
        finally:
            pass

    async def load_cookie_files(self) -> None:
        if self.manager.config_manager.settings_data.browser_cookies.auto_import:
            assert self.manager.config_manager.settings_data.browser_cookies.browser
            get_cookies_from_browsers(
                self.manager, browser=self.manager.config_manager.settings_data.browser_cookies.browser
            )
        cookie_files = sorted(self.manager.path_manager.cookies_dir.glob("*.txt"))
        if not cookie_files:
            return
        async for domain, cookie in read_netscape_files(cookie_files):
            self.cookies.update_cookies(cookie, response_url=AbsoluteHttpURL(f"https://{domain}"))

        log_spacer(20, log_to_console=False)

    async def get_downloader_spacer(self, key: str) -> float:
        """Returns the download spacer for a domain."""
        if key in self.download_spacer:
            return self.download_spacer[key]
        return 0.1

    async def get_rate_limiter(self, domain: str) -> AsyncLimiter:
        """Get a rate limiter for a domain."""
        if domain in self.domain_rate_limits:
            return self.domain_rate_limits[domain]
        return self.domain_rate_limits["other"]

    @classmethod
    async def check_http_status(
        cls,
        response: ClientResponse | CurlResponse | CachedResponse,
        download: bool = False,
    ) -> BeautifulSoup | None:
        """Checks the HTTP status code and raises an exception if it's not acceptable.

        If the response is successful and has valid html, returns soup
        """
        status: int = response.status_code if hasattr(response, "status_code") else response.status  # type: ignore
        content_type: str = getattr(response, "content_type", None) or response.headers.get("Content-Type", "")
        headers = response.headers
        url_host: str = AbsoluteHttpURL(response.url).host
        message = None

        def check_etag() -> None:
            if download and (e_tag := headers.get("ETag")) in DOWNLOAD_ERROR_ETAGS:
                message = DOWNLOAD_ERROR_ETAGS[e_tag]
                raise DownloadError(HTTPStatus.NOT_FOUND, message=message)

        async def check_ddos_guard() -> BeautifulSoup | None:
            if "html" not in content_type:
                return

            # TODO: use the response text instead of the raw content to prevent double encoding detection

            if soup := await get_soup_no_error(response):
                if cls.check_ddos_guard(soup) or cls.check_cloudflare(soup):
                    raise DDOSGuardError
                return soup

        async def check_json_status() -> None:
            if "json" not in content_type:
                return

            # TODO: Define these checks inside their actual crawlers
            # and make them register them  on instantation
            if not any(domain in url_host for domain in ("gofile", "imgur")):
                return

            with contextlib.suppress(ContentTypeError):
                json_resp: dict[str, Any] | None = await response.json()
                if not json_resp:
                    return
                json_status: str | int | None = json_resp.get("status")
                if json_status and isinstance(status, str) and "notFound" in status:
                    raise ScrapeError(404)

                if (data := json_resp.get("data")) and isinstance(data, dict) and "error" in data:
                    raise ScrapeError(json_status or status, data["error"])

        check_etag()
        if HTTPStatus.OK <= status < HTTPStatus.BAD_REQUEST:
            # Check DDosGuard even on successful pages
            # await check_ddos_guard()
            return

        await check_json_status()
        await check_ddos_guard()
        raise DownloadError(status=status, message=message)

    @staticmethod
    def check_content_length(headers: Mapping[str, Any]) -> None:
        content_length, content_type = headers.get("Content-Length"), headers.get("Content-Type")
        if content_length is None or content_type is None:
            return
        if content_length == "322509" and content_type == "video/mp4":
            raise DownloadError(status="Bunkr Maintenance", message="Bunkr under maintenance")
        if content_length == "73003" and content_type == "video/mp4":
            raise DownloadError(410)  # Placeholder video with text "Video removed" (efukt)

    @staticmethod
    def check_ddos_guard(soup: BeautifulSoup) -> bool:
        if (title := soup.select_one("title")) and (title_str := title.string):
            if any(title.casefold() == title_str.casefold() for title in DDosGuard.TITLES):
                return True

        return bool(soup.select_one(DDosGuard.ALL_SELECTORS))

    @staticmethod
    def check_cloudflare(soup: BeautifulSoup) -> bool:
        if (title := soup.select_one("title")) and (title_str := title.string):
            if any(title.casefold() == title_str.casefold() for title in CloudflareTurnstile.TITLES):
                return True

        return bool(soup.select_one(CloudflareTurnstile.ALL_SELECTORS))

    async def close(self) -> None:
        await self.flaresolverr._destroy_session()


@dataclass(frozen=True, slots=True)
class FlaresolverrResponse:
    status: str
    cookies: dict
    user_agent: str
    soup: BeautifulSoup | None
    url: AbsoluteHttpURL

    @classmethod
    def from_dict(cls, flaresolverr_resp: dict) -> FlaresolverrResponse:
        status = flaresolverr_resp["status"]
        solution: dict = flaresolverr_resp["solution"]
        response = solution["response"]
        user_agent = solution["userAgent"].strip()
        url_str: str = solution["url"]
        cookies: dict = solution.get("cookies") or {}
        soup = BeautifulSoup(response, "html.parser") if response else None
        url = AbsoluteHttpURL(url_str)
        return cls(status, cookies, user_agent, soup, url)


class Flaresolverr:
    """Class that handles communication with flaresolverr."""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self.enabled = bool(client_manager.manager.global_config.general.flaresolverr)
        self.session_id: str = ""
        self.session_lock = asyncio.Lock()
        self.request_lock = asyncio.Lock()
        self.request_count = 0

    async def _request(
        self,
        command: str,
        client_session: ClientSession,
        **kwargs,
    ) -> dict:
        """Base request function to call flaresolverr."""
        if not self.enabled:
            raise DDOSGuardError(message="FlareSolverr is not configured")
        async with self.session_lock:
            if not (self.session_id or kwargs.get("session")):
                await self._create_session()
        return await self._make_request(command, client_session, **kwargs)

    async def _make_request(self, command: str, client_session: ClientSession, **kwargs) -> dict[str, Any]:
        timeout = self.client_manager.manager.global_config.rate_limiting_options._scrape_timeout
        if command == "sessions.create":
            timeout = aiohttp.ClientTimeout(total=5 * 60, connect=60)  # 5 minutes to create session

        for key, value in kwargs.items():
            if isinstance(value, AbsoluteHttpURL):
                kwargs[key] = str(value)

        data = {
            "cmd": command,
            "maxTimeout": 60_000,  # This timeout is in miliseconds (60s)
            "session": self.session_id,
        } | kwargs

        self.request_count += 1
        msg = f"Waiting For Flaresolverr Response [{self.request_count}]"
        assert self.client_manager.manager.global_config.general.flaresolverr
        async with (
            self.request_lock,
            self.client_manager.manager.progress_manager.show_status_msg(msg),
        ):
            response = await client_session.post(
                self.client_manager.manager.global_config.general.flaresolverr / "v1",
                json=data,
                timeout=timeout,
            )
            json_obj: dict[str, Any] = await response.json()

        return json_obj

    async def _create_session(self) -> None:
        """Creates a permanet flaresolverr session."""
        session_id = "cyberdrop-dl"
        async with self.client_manager._new_session() as client_session:
            flaresolverr_resp = await self._make_request("sessions.create", client_session, session=session_id)
        status = flaresolverr_resp.get("status")
        if status != "ok":
            raise DDOSGuardError(message="Failed to create flaresolverr session")
        self.session_id = session_id

    async def _destroy_session(self) -> None:
        if self.session_id:
            async with self.client_manager._new_session() as client_session:
                await self._make_request("sessions.destroy", client_session, session=self.session_id)
            self.session_id = ""

    async def get(
        self,
        url: AbsoluteHttpURL,
        client_session: ClientSession,
        update_cookies: bool = True,
    ) -> tuple[BeautifulSoup | None, AbsoluteHttpURL]:
        """Returns the resolved URL from the given URL."""
        json_resp: dict = await self._request("request.get", client_session, url=url)

        try:
            fs_resp = FlaresolverrResponse.from_dict(json_resp)
        except (AttributeError, KeyError):
            raise DDOSGuardError(message="Invalid response from flaresolverr") from None

        if fs_resp.status != "ok":
            raise DDOSGuardError(message="Failed to resolve URL with flaresolverr")

        user_agent = client_session.headers["User-Agent"].strip()
        mismatch_msg = f"Config user_agent and flaresolverr user_agent do not match: \n  Cyberdrop-DL: '{user_agent}'\n  Flaresolverr: '{fs_resp.user_agent}'"
        if fs_resp.soup and (
            self.client_manager.check_ddos_guard(fs_resp.soup) or self.client_manager.check_cloudflare(fs_resp.soup)
        ):
            if not update_cookies:
                raise DDOSGuardError(message="Invalid response from flaresolverr")
            if fs_resp.user_agent != user_agent:
                raise DDOSGuardError(message=mismatch_msg)

        if update_cookies:
            if fs_resp.user_agent != user_agent:
                log(f"{mismatch_msg}\nResponse was successful but cookies will not be valid", 30)

            for cookie in fs_resp.cookies:
                self.client_manager.cookies.update_cookies(
                    {cookie["name"]: cookie["value"]}, AbsoluteHttpURL(f"https://{cookie['domain']}")
                )

        return fs_resp.soup, fs_resp.url


async def _set_dns_resolver(loop: asyncio.AbstractEventLoop | None = None) -> None:
    if constants.DNS_RESOLVER is not None:
        return
    try:
        await _test_async_resolver(loop)
        constants.DNS_RESOLVER = aiohttp.AsyncResolver
    except Exception as e:
        constants.DNS_RESOLVER = aiohttp.ThreadedResolver
        log(f"Unable to setup asynchronous DNS resolver. Falling back to thread based resolver: {e}", 30)


async def _test_async_resolver(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Test aiodns with a DNS lookup."""

    # pycares (the underlying C extension library that aiodns uses) installs successfully in most cases,
    # but it fails to actually connect to DNS servers on some platforms (e.g., Android).
    import aiodns

    async with aiodns.DNSResolver(loop=loop, timeout=5.0) as resolver:
        _ = await resolver.query("github.com", "A")


def _create_request_log_hooks(client_type: Literal["scrape", "download"]) -> list[aiohttp.TraceConfig]:
    async def on_request_start(*args) -> None:
        params: aiohttp.TraceRequestStartParams = args[2]
        log_debug(f"Starting {client_type} {params.method} request to {params.url}", 10)

    async def on_request_end(*args) -> None:
        params: aiohttp.TraceRequestEndParams = args[2]
        msg = f"Finishing {client_type} {params.method} request to {params.url}"
        msg += f" -> response status: {params.response.status}"
        log_debug(msg, 10)

    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)
    return [trace_config]
