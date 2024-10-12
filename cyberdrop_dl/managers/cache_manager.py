from __future__ import annotations

from dataclasses import field
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING, Optional

import yaml
from aiohttp import ClientResponse
from aiohttp_client_cache import SQLiteBackend
from bs4 import BeautifulSoup

from cyberdrop_dl.utils.dataclasses.supported_domains import SupportedDomains
from cyberdrop_dl.utils.utilities import log, DEBUG_VAR

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def _save_yaml(file: Path, data: Dict) -> None:
    """Saves a dict to a yaml file"""
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, 'w') as yaml_file:
        yaml.dump(data, yaml_file)


def _load_yaml(file: Path) -> Dict:
    """Loads a yaml file and returns it as a dict"""
    with open(file, 'r') as yaml_file:
        return yaml.load(yaml_file.read(), Loader=yaml.FullLoader)


class CacheManager:
    def __init__(self, manager: 'Manager'):
        self.manager = manager

        self.request_cache: SQLiteBackend = field(init=False)
        self.cache_file: Path = field(init=False)
        self._cache = {}

        self.return_values = {}

    def startup(self, cache_file: Path) -> None:
        """Ensures that the cache file exists"""
        self.cache_file = cache_file
        if not self.cache_file.is_file():
            self.save('default_config', "Default")

        self.load()
        if self.manager.args_manager.appdata_dir:
            self.save('first_startup_completed', True)

    def load(self) -> None:
        """Loads the cache files into memory"""
        self._cache = _load_yaml(self.cache_file)

    async def set_return_value(self, url: str, value: bool, pop: Optional[bool] = True) -> None:
        """Sets a return value for a url"""
        self.return_values[url] = (value, pop)

    async def get_return_value(self, url: str) -> Optional[bool]:
        """Gets a return value for a url"""
        value, pop = self.return_values.get(url, None)
        if pop:
            self.return_values.pop(url, None)
        return value

    async def filter_fn(self, response: ClientResponse) -> bool:
        """Filter function for aiohttp_client_cache"""
        HTTP_404_LIKE_STATUS = {HTTPStatus.NOT_FOUND, HTTPStatus.GONE, HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS}

        if response.status in HTTP_404_LIKE_STATUS:
            return True

        if response.url in self.return_values:
            return self.get_return_value(response.url)

        async def check_simpcity_page(response: ClientResponse):
            """Checks if the last page has been reached"""

            final_page_selector = "li.pageNav-page a"
            current_page_selector = "li.pageNav-page.pageNav-page--current a"

            soup = BeautifulSoup(await response.text(), "html.parser")
            try:
                last_page = int(soup.select(final_page_selector)[-1].text.split('page-')[-1])
                current_page = int(soup.select_one(current_page_selector).text.split('page-')[-1])
            except AttributeError:
                return False, "Last page not found, assuming only one page"
            return current_page != last_page, "Last page not reached" if current_page != last_page else "Last page reached"

        async def check_coomer_page(response: ClientResponse):
            """Checks if the last page has been reached"""
            url_part_responses = {'data': "Data page", "onlyfans": "Onlyfans page", "fansly": "Fansly page"}
            if response.url.parts[1] in url_part_responses:
                return False, url_part_responses[response.url.parts[1]]
            current_offset = int(response.url.query.get("o", 0))
            maximum_offset = int(response.url.query.get("omax", 0))
            return current_offset != maximum_offset, "Last page not reached" if current_offset != maximum_offset else "Last page reached"

        filter_dict = {"simpcity.su": check_simpcity_page, "coomer.su": check_coomer_page}

        filter_fn=filter_dict.get(response.url.host)
        cache_response, reason = await filter_fn(response) if filter_fn else False, "No caching manager for host"
        return cache_response

    def load_request_cache(self) -> None:
        urls_expire_after = {'*.simpcity.su': self.manager.config_manager.global_settings_data['Rate_Limiting_Options'][
            'file_host_cache_length']}
        for host in SupportedDomains.supported_hosts:
            urls_expire_after[f'*.{host}' if '.' in host else f'*.{host}.*'] = \
            self.manager.config_manager.global_settings_data['Rate_Limiting_Options']['file_host_cache_length']
        for forum in SupportedDomains.supported_forums:
            urls_expire_after[f'{forum}'] = self.manager.config_manager.global_settings_data['Rate_Limiting_Options'][
                'forum_cache_length']
        self.request_cache = SQLiteBackend(
            cache_name=self.manager.path_manager.cache_db,
            autoclose=False,
            allowed_codes=(
                HTTPStatus.OK,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.GONE,
                HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS),
            allowed_methods=['GET'],
            expire_after=timedelta(days=7),
            urls_expire_after=urls_expire_after,
            filter_fn=self.filter_fn
        )

    def get(self, key: str) -> Any:
        """Returns the value of a key in the cache"""
        return self._cache.get(key, None)

    def save(self, key: str, value: Any) -> None:
        """Saves a key and value to the cache"""
        self._cache[key] = value
        _save_yaml(self.cache_file, self._cache)

    def remove(self, key: str) -> None:
        """Removes a key from the cache"""
        if key in self._cache:
            del self._cache[key]
            _save_yaml(self.cache_file, self._cache)

    async def close(self):
        await self.request_cache.close()
