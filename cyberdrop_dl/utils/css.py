from __future__ import annotations

import functools
from typing import TYPE_CHECKING, NamedTuple, ParamSpec, TypeVar

import bs4.css

from cyberdrop_dl.exceptions import ScrapeError

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from bs4 import Tag

P = ParamSpec("P")
R = TypeVar("R")


class SelectorError(ScrapeError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(422, message)


class CssAttributeSelector(NamedTuple):
    element: str
    attribute: str = ""

    def __call__(self, soup: Tag) -> str:
        return select_one_get_attr(soup, self.element, self.attribute)


def not_none(func: Callable[P, R | None]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        result = func(*args, **kwargs)
        if result is None:
            raise SelectorError
        return result

    return wrapper


@not_none
def select_one(tag: Tag, selector: str) -> Tag | None:
    """Same as `tag.select_one` but asserts the result is not `None`"""
    return tag.select_one(selector)


def select_one_get_text(tag: Tag, selector: str, strip: bool = True, *, decompose: str | None = None) -> str:
    """Same as `tag.select_one.get_text(strip=strip)` but asserts the result is not `None`"""
    inner_tag = select_one(tag, selector)
    if decompose:
        for trash in iselect(inner_tag, decompose):
            trash.decompose()
    return get_text(inner_tag, strip)


# TODO: Rename this to just get_attr
# get_attr_no_error should be get_attr_or_none. `or_none` implies no error
def get_attr_or_none(tag: Tag, attribute: str) -> str | None:
    """Same as `tag.get(attribute)` but asserts the result is a single str"""
    attribute_ = attribute
    if attribute_ == "srcset" and (srcset := tag.get(attribute_)):
        if isinstance(srcset, str):
            return _parse_srcset(srcset)
        attribute_ = "src"

    if attribute_ == "src":
        value = tag.get("data-src") or tag.get(attribute_)
    else:
        value = tag.get(attribute_)
    if isinstance(value, list):
        raise SelectorError(f"Expected a single value for {attribute = !r}, got multiple")
    return value


def get_attr_no_error(tag: Tag, attribute: str) -> str | None:
    try:
        return get_attr_or_none(tag, attribute)
    except Exception:
        return


def get_text(tag: Tag, strip: bool = True) -> str:
    return tag.get_text(strip=strip)


@not_none
def get_attr(tag: Tag, attribute: str) -> str | None:
    """Same as `tag.get(attribute)` but asserts the result is not `None` and is a single string"""
    return get_attr_or_none(tag, attribute)


def select_one_get_attr(tag: Tag, selector: str, attribute: str) -> str:
    """Same as `tag.select_one(selector)[attribute]` but asserts the result is not `None` and is a single string"""
    inner_tag = select_one(tag, selector)
    return get_attr(inner_tag, attribute)


def select_one_get_attr_or_none(tag: Tag, selector: str, attribute: str) -> str | None:
    if inner_tag := tag.select_one(selector):
        return get_attr_or_none(inner_tag, attribute)


def iselect(tag: Tag, selector: str) -> Generator[Tag]:
    """Same as `tag.select(selector)`, but it returns a generator instead of a list."""
    yield from bs4.css.CSS(tag).iselect(selector)


def _parse_srcset(srcset: str) -> str:
    # The best src is the last one (usually)
    return [src.split(" ")[0] for src in srcset.split(", ")][-1]


def iget(tag: Tag, selector: str, attribute: str) -> Generator[str]:
    for inner_tag in iselect(tag, selector):
        if link := get_attr_or_none(inner_tag, attribute):
            yield link


def decompose(tag: Tag, selector: str) -> None:
    for inner_tag in tag.select(selector):
        inner_tag.decompose()


iframes = CssAttributeSelector("iframe", "src")
images = CssAttributeSelector("img", "srcset")
links = CssAttributeSelector(":any-link", "href")
