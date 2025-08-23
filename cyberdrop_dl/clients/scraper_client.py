from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from json import dumps as json_dumps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import cyberdrop_dl.constants as constants
from cyberdrop_dl.clients.response import AbstractResponse
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, copy_signature
from cyberdrop_dl.exceptions import DDOSGuardError, DownloadError, InvalidContentTypeError
from cyberdrop_dl.utils.utilities import sanitize_filename

if TYPE_CHECKING:
    from bs4 import BeautifulSoup
    from curl_cffi.requests.impersonate import BrowserTypeLiteral
    from curl_cffi.requests.session import HttpMethod

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
    async def _limiter(self, domain: str):
        with self.client_manager.request_context(domain):
            domain_limiter = self.client_manager.get_rate_limiter(domain)
            async with self.client_manager.global_rate_limiter, domain_limiter:
                await self.client_manager.manager.states.RUNNING.wait()
                yield

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
        request_params["headers"] = self.client_manager._default_headers | (headers or {})
        request_params["data"] = data
        request_params["json"] = json

        if impersonate:
            self.client_manager.check_curl_cffi_is_available()
            if impersonate is True:
                impersonate = "chrome"
            request_params["impersonate"] = impersonate
            response = await self.client_manager._curl_session.request(method, str(url), **request_params)

        else:
            async with self.client_manager.cache_control(self.client_manager._session, disabled=cache_disabled):
                response = await self.client_manager._session._request(method, url, **request_params)

        abs_resp = AbstractResponse(response)
        exc = None
        try:
            await self.client_manager.check_http_status(response)
        except (DDOSGuardError, DownloadError) as e:
            exc = e
            raise

        else:
            if impersonate:
                self.client_manager.cookies.update_cookies(
                    self.client_manager._curl_session.cookies.get_dict(url.host), url
                )
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
