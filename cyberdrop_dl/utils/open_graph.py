from __future__ import annotations

import dataclasses
import inspect
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import bs4

V = TypeVar("V")
R = TypeVar("R")


def get_valid_kwargs(func: Callable[..., Any], kwargs: Mapping[str, V], accept_kwargs: bool = True) -> Mapping[str, V]:
    """Get the subset of ``kwargs`` that are valid params for ``func`` and their values are not `None`

    If func takes **kwargs, returns everything"""
    params = inspect.signature(func).parameters
    if accept_kwargs and any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs

    return {k: v for k, v in kwargs.items() if k in params.keys() and v is not None}


def call_w_valid_kwargs(cls: Callable[..., R], kwargs: Mapping[str, Any]) -> R:
    return cls(**get_valid_kwargs(cls, kwargs))


@dataclasses.dataclass(frozen=True, slots=True)
class OpenGraph:
    """Open Graph properties.  Each attribute corresponds to an OG property."""

    required_attrs = ("title", "type", "image", "url", "description")

    audio: str | None = None
    description: str | None = None
    determiner: str | None = None
    image: str | None = None
    image: str | None = None
    locale: str | None = None
    published_time: str | None = None
    site_name: str | None = None
    title: str | None = None
    type: str | None = None
    url: str | None = None
    video: str | None = None

    def is_valid(self) -> bool:
        return all(getattr(self, attr, False) for attr in self.required_attrs)


_og_fields = dataclasses.fields(OpenGraph)


def parse(soup: bs4.BeautifulSoup) -> OpenGraph:
    """Extracts Open Graph properties (og properties) from soup."""
    props: dict[str, str | None] = {}
    for meta in soup.select('meta[property^="og:"][content]'):
        property_name = meta["property"].replace("og:", "")  # type: ignore
        if property_name in _og_fields:
            props[property_name] = meta["content"] or None  # type: ignore

    if not props.get("title") and (title := soup.select_one("title, h1")):
        props["title"] = title.get_text(strip=True) or None

    return OpenGraph(**props)


def get(name: str, /, soup: bs4.BeautifulSoup) -> str | None:
    if meta := soup.select_one(f'meta[property^="og:{name}"][content]'):
        return meta["content"] or None  # type: ignore


def get_title(soup: bs4.BeautifulSoup) -> str | None:
    return get("title", soup)
