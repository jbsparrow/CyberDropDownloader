from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import TypeIs

if TYPE_CHECKING:
    from collections.abc import Iterable

    import yarl

    from cyberdrop_dl.url_objects import AbsoluteHttpURL


def fix_query_params_encoding(link: str) -> str:
    if "?" not in link:
        return link
    parts, query_and_frag = link.split("?", 1)
    query_and_frag = query_and_frag.replace("+", "%20")
    return f"{parts}?{query_and_frag}"


def fix_multi_slashes(url: str) -> str:
    import re

    return re.sub(r"(^/|https?:/)/+", r"\1/", url, count=1)


def str_to_url(url: str) -> yarl.URL:
    import yarl

    if not url:
        raise ValueError("Empty URL", url)

    clean_url = fix_multi_slashes(fix_query_params_encoding(url))
    return yarl.URL(clean_url, encoded="%" in clean_url)


def parse_http_url(
    link: yarl.URL | str,
    relative_to: AbsoluteHttpURL | None = None,
    *,
    trim: bool = True,
) -> AbsoluteHttpURL:
    """Parse a string into an absolute URL, handling relative URLs, encoding and optionally removes trailing slash (trimming)."""

    url = str_to_url(link) if isinstance(link, str) else link
    if not _is_absolute_http_url(url):
        if not relative_to:
            raise ValueError("Relative URL with no known origin", url)
        url = resolve_url(url, relative_to)

    check_url(url)
    if not trim:
        return url
    return remove_trailing_slash(url)


def resolve_url(url: yarl.URL, origin: AbsoluteHttpURL) -> AbsoluteHttpURL:
    url = origin.join(url) if not url.absolute else url
    if not url.scheme:
        url = url.with_scheme(origin.scheme if origin else "https")
    if not _is_absolute_http_url(url):
        raise ValueError(f"Unable to parse an absolute URL from {url}")
    return url


def check_url(url: yarl.URL) -> None:
    if not url.host:
        raise ValueError("URL has no host", url)
    if "." not in url.host and url.host != "localhost":
        raise ValueError("URL has no TLD", url)


def remove_trailing_slash(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    if url.name or url.path == "/":
        return url
    return url.parent.with_fragment(url.fragment).with_query(url.query)


def matches_any_host(url: yarl.URL, hosts: Iterable[str]) -> bool:
    import yarl

    if not url.host:
        return False

    assert not isinstance(hosts, str)
    for host in hosts:
        if host in url.host:
            return True
        if host.startswith(("https://", "http://")) and yarl.URL(host).host == url.host:
            return True

    return False


def _is_absolute_http_url(url: yarl.URL) -> TypeIs[AbsoluteHttpURL]:
    return url.absolute and url.scheme in {"http", "https"}
