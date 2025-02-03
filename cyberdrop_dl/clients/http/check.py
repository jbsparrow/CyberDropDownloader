from __future__ import annotations

import contextlib
from http import HTTPStatus
from typing import TYPE_CHECKING

from aiohttp import ClientResponse, ContentTypeError
from bs4 import BeautifulSoup

from cyberdrop_dl.clients.errors import DDOSGuardError, DownloadError, ScrapeError
from cyberdrop_dl.utils.constants import CustomHTTPStatus

if TYPE_CHECKING:
    from multidict import CIMultiDictProxy
    from yarl import URL

    from cyberdrop_dl.scraper.crawler import ScrapeItem


DOWNLOAD_ERROR_ETAGS = {
    "d835884373f4d6c8f24742ceabe74946": "Imgur image has been removed",
    "65b7753c-528a": "SC Scrape Image",
    "5c4fb843-ece": "PixHost Removed Image",
}


CLOUDFLARE_CHALLENGE_TITLES = ["Simpcity Cuck Detection", "Attention Required! | Cloudflare"]
CLOUDFLARE_CHALLENGE_SELECTORS = ["captchawrapper", "cf-turnstile"]
DDOS_GUARD_CHALLENGE_TITLES = ["Just a moment...", "DDoS-Guard"]
DDOS_GUARD_CHALLENGE_SELECTORS = [
    "#cf-challenge-running",
    ".ray_id",
    ".attack-box",
    "#cf-please-wait",
    "#challenge-spinner",
    "#trk_jschal_js",
    "#turnstile-wrapper",
    ".lds-ring",
]


ALL_TITLES = DDOS_GUARD_CHALLENGE_TITLES + CLOUDFLARE_CHALLENGE_TITLES
ALL_SELECTORS = DDOS_GUARD_CHALLENGE_SELECTORS + CLOUDFLARE_CHALLENGE_SELECTORS


def is_bunkr_maintenance(headers: CIMultiDictProxy[str] | dict) -> bool:
    return headers.get("Content-Length") == "322509" and headers.get("Content-Type") == "video/mp4"


def is_ddos_guard(soup: BeautifulSoup) -> bool:
    return is_in_soup(soup, ALL_TITLES, ALL_SELECTORS)


def is_in_soup(soup: BeautifulSoup, titles: list[str], selectors: list[str]) -> bool:
    if soup.title:
        for title in titles:
            challenge_found = title.casefold() == soup.title.text.casefold()
            if challenge_found:
                return True

    for selector in selectors:
        challenge_found = soup.find(selector)
        if challenge_found:
            return True

    return False


async def raise_for_http_status(
    response: ClientResponse, download: bool = False, origin: ScrapeItem | URL | None = None
) -> None:
    """Checks the HTTP status code and raises an exception if it's not acceptable."""
    status = response.status
    headers = response.headers

    e_tag = headers.get("ETag")
    if download and e_tag and e_tag in DOWNLOAD_ERROR_ETAGS:
        message = DOWNLOAD_ERROR_ETAGS.get(e_tag)
        raise DownloadError(HTTPStatus.NOT_FOUND, message=message, origin=origin)

    if HTTPStatus.OK <= status < HTTPStatus.BAD_REQUEST:
        return

    assert response.url.host
    if any(domain in response.url.host for domain in ("gofile", "imgur")):
        with contextlib.suppress(ContentTypeError):
            JSON_Resp: dict = await response.json()
            status_str: str = JSON_Resp.get("status")  # type: ignore
            if status_str and isinstance(status, str) and "notFound" in status_str:
                raise ScrapeError(404, origin=origin)
            data = JSON_Resp.get("data")
            if data and isinstance(data, dict) and "error" in data:
                raise ScrapeError(status_str, data["error"], origin=origin)

    response_text = None
    with contextlib.suppress(UnicodeDecodeError):
        response_text = await response.text()

    if response_text:
        soup = BeautifulSoup(response_text, "html.parser")
        if is_ddos_guard(soup):
            raise DDOSGuardError(origin=origin)
    status: str | int = status if headers.get("Content-Type") else CustomHTTPStatus.IM_A_TEAPOT
    message = None if headers.get("Content-Type") else "No content-type in response header"

    raise DownloadError(status=status, message=message, origin=origin)
