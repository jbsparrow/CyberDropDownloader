from __future__ import annotations

import asyncio
import re
import warnings
from contextlib import contextmanager
from dataclasses import field
from re import Pattern
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from realdebrid import RealDebrid
from realdebrid.exceptions import APIError, InvalidTokenException, RealDebridError

from cyberdrop_dl.clients.errors import DebridError
from cyberdrop_dl.utils.logger import log

warnings.simplefilter(action="ignore", category=FutureWarning)

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager

FOLDER_AS_PART = {"folder", "folders", "dir"}
FOLDER_AS_QUERY = {"sharekey"}
RATE_LIMITS = {"real-debrid": 250}


class DebridManager:
    debrid_service = "real-debrid"

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.__api_token = self.manager.config_manager.authentication_data.realdebrid.api_key
        self.limiter = AsyncLimiter(RATE_LIMITS[self.debrid_service], 1)
        self.enabled = bool(self.__api_token)
        self.file_regex: Pattern = field(init=False)
        self.folder_regex: Pattern = field(init=False)
        self.supported_regex: Pattern = field(init=False)
        self.api: RealDebrid = field(init=False)

    async def get_regex(self) -> tuple[str, str]:
        calls = [self.api.hosts.regex(), self.api.hosts.regex_folder()]
        responses = await asyncio.gather(*calls)
        return tuple([(await r.json())[1:-1] for r in responses])

    async def startup(self) -> None:
        """Startup process for Debrid manager."""
        if not self.enabled:
            return
        try:
            with catch_error():
                return await self.async_startup()
        except DebridError as e:
            log(f"Failed RealDebrid setup: {e!s}", 40)
            self.enabled = False

    async def async_startup(self) -> None:
        self.api = RealDebrid(self.__api_token)
        file_regex, folder_regex = await self.get_regex()
        regex = "|".join(file_regex + folder_regex)
        file_regex = "|".join(file_regex)
        folder_regex = "|".join(folder_regex)
        self.supported_regex = re.compile(regex)
        self.file_regex = re.compile(file_regex)
        self.folder_regex = re.compile(folder_regex)

    def is_supported_folder(self, url: URL) -> bool:
        with catch_error():
            match = self.folder_regex.search(str(url))
            return bool(match)

    def is_supported_file(self, url: URL) -> bool:
        with catch_error():
            match = self.file_regex.search(str(url))
            return bool(match)

    def is_supported(self, url: URL) -> bool:
        with catch_error():
            assert url.host, f"{url} has no host"
            match = self.supported_regex.search(str(url))
            return bool(match) or "real-debrid" in url.host.lower()

    async def unrestrict_link(self, url: URL, password: str = "") -> str:
        with catch_error():
            resp = await self.api.unrestrict.link(url, password)  # type: ignore
            json = await resp.json()
            return json["download"]

    async def unrestrict_folder(self, url: URL) -> list[str]:
        with catch_error():
            resp = await self.api.unrestrict.folder(url)  # type: ignore
            json = await resp.json()
            return list(json)

    def guess_folder(self, url: URL) -> str:
        for guess_function in folder_guess_functions:
            folder = guess_function(url)
            if folder:
                return folder
        return url.path


@contextmanager
def catch_error():
    try:
        yield
    except (RealDebridError, InvalidTokenException, APIError) as e:
        raise DebridError(str(e)) from None


def guess_folder_by_part(url: URL) -> str | None:
    for word in FOLDER_AS_PART:
        if word in url.parts:
            index = url.parts.index(word)
            if index + 1 < len(url.parts):
                return url.parts[index + 1]
    return None


def guess_folder_by_query(url: URL) -> str | None:
    for word in FOLDER_AS_QUERY:
        folder = url.query.get(word)
        if folder:
            return folder
    return None


folder_guess_functions = [guess_folder_by_part, guess_folder_by_query]
