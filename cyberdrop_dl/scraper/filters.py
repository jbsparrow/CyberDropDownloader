from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import arrow
from aiohttp import ClientResponse
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError
from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.utilities import get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem


return_values = {}


def is_valid_url(scrape_item: ScrapeItem) -> bool:
    if not scrape_item.url:
        return False
    if not isinstance(scrape_item.url, URL):
        try:
            scrape_item.url = URL(scrape_item.url)
        except AttributeError:
            return False
    try:
        if not scrape_item.url.host:
            return False
    except AttributeError:
        return False

    return True


def is_outside_date_range(scrape_item: ScrapeItem, before: arrow, after: arrow) -> bool:
    skip = False
    item_date = scrape_item.completed_at or scrape_item.created_at
    if not item_date:
        return False
    if after and arrow.get(item_date) < after or before and arrow.get(item_date) > before:
        skip = True

    return skip


def is_in_domain_list(scrape_item: ScrapeItem, domain_list: list[str]) -> bool:
    return any(domain in scrape_item.url.host for domain in domain_list)


def remove_trailing_slash(url: URL) -> URL:
    if not str(url).endswith("/"):
        return url

    url_trimmed = url.with_path(url.path[:-1])
    if url.query_string:
        query = url.query_string[:-1]
        url_trimmed = url.with_query(query)

    return url_trimmed


def has_valid_extension(url: URL) -> bool:
    """Checks if the URL has a valid extension."""
    try:
        _, ext = get_filename_and_ext(url.name)
        valid_exts = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"] | FILE_FORMATS["Audio"]
    except NoExtensionError:
        return False
    else:
        return ext in valid_exts


async def set_return_value(url: str, value: bool, pop: bool | None = True) -> None:
    """Sets a return value for a url"""
    global return_values
    return_values[url] = (value, pop)


async def get_return_value(url: str) -> bool | None:
    """Gets a return value for a url"""
    global return_values
    value, pop = return_values.get(url, None)
    if pop:
        return_values.pop(url, None)
    return value


async def filter_fn(response: ClientResponse) -> bool:
    """Filter function for aiohttp_client_cache"""
    HTTP_404_LIKE_STATUS = {HTTPStatus.NOT_FOUND, HTTPStatus.GONE, HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS}

    if response.status in HTTP_404_LIKE_STATUS:
        return True

    if response.url in return_values:
        return get_return_value(response.url)

    async def check_simpcity_page(response: ClientResponse):
        """Checks if the last page has been reached"""

        final_page_selector = "li.pageNav-page a"
        current_page_selector = "li.pageNav-page.pageNav-page--current a"

        soup = BeautifulSoup(await response.text(), "html.parser")
        try:
            last_page = int(soup.select(final_page_selector)[-1].text.split("page-")[-1])
            current_page = int(soup.select_one(current_page_selector).text.split("page-")[-1])
        except (AttributeError, IndexError):
            return False, "Last page not found, assuming only one page"
        return current_page != last_page, "Last page not reached" if current_page != last_page else "Last page reached"

    async def check_coomer_page(response: ClientResponse):
        """Checks if the last page has been reached"""
        url_part_responses = {"data": "Data page", "onlyfans": "Onlyfans page", "fansly": "Fansly page"}
        if response.url.parts[1] in url_part_responses:
            return False, url_part_responses[response.url.parts[1]]
        current_offset = int(response.url.query.get("o", 0))
        maximum_offset = int(response.url.query.get("omax", 0))
        return (
            current_offset != maximum_offset,
            "Last page not reached" if current_offset != maximum_offset else "Last page reached",
        )

    async def check_kemono_page(response: ClientResponse):
        url_part_responses = {
            "data": "Data page",
            "afdian": "Afdian page",
            "boosty": "Boosty page",
            "dlsite": "Dlsite page",
            "fanbox": "Fanbox page",
            "fantia": "Fantia page",
            "gumroad": "Gumroad page",
            "patreon": "Patreon page",
            "subscribestar": "Subscribestar page",
            "discord": "Discord page",
        }
        if response.url.parts[1] in url_part_responses:
            return False, url_part_responses[response.url.parts[1]]
        elif "discord/channel" in response.url.parts:
            return False, "Discord channel page"
        current_offset = int(response.url.query.get("o", 0))
        maximum_offset = int(response.url.query.get("omax", 0))
        return (
            current_offset != maximum_offset,
            "Last page not reached" if current_offset != maximum_offset else "Last page reached",
        )

    filter_dict = {"simpcity.su": check_simpcity_page, "coomer.su": check_coomer_page, "kemono.su": check_kemono_page}

    filter_fn = filter_dict.get(response.url.host)
    cache_response, reason = await filter_fn(response) if filter_fn else False, "No caching manager for host"
    return cache_response
