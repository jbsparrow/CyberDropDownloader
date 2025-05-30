from __future__ import annotations

import functools
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from bs4 import Tag

P = ParamSpec("P")
R = TypeVar("R")


def not_none(func: Callable[P, R | None]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        result = func(*args, **kwargs)
        assert result is not None
        return result

    return wrapper


def select_one(tag: Tag, selector: str) -> Tag:
    """Same as `tag.select_one` but asserts the result is not `None`"""
    return not_none(tag.select_one)(selector)


def select_one_get_text(tag: Tag, selector: str, strip: bool = True) -> str:
    """Same as `tag.select_one` but asserts the result is not `None`"""
    return get_text(select_one(tag, selector), strip)


def get_attr_or_none(tag: Tag, attribute: str) -> str | None:
    """Same as `tag.get(attribute)` but asserts the result is not multiple strings"""
    value = tag.get(attribute)
    assert not isinstance(value, list)
    return value


def get_text(tag: Tag, strip: bool = True) -> str:
    return tag.get_text(strip=strip)


def get_attr(tag: Tag, attribute: str) -> str:
    """Same as `tag.get(attribute)` but asserts the result is not `None` and is a single string"""
    return not_none(get_attr_or_none)(tag, attribute)


def select_one_get_attr(tag: Tag, selector: str, attribute: str) -> str:
    """Same as `tag.select_one(selector)[attribute]` but asserts the result is not `None` and is a single string"""
    inner_tag = select_one(tag, selector)
    return get_attr(inner_tag, attribute)


def select_one_get_attr_or_none(tag: Tag, selector: str, attribute: str) -> str | None:
    if inner_tag := tag.select_one(selector):
        return get_attr_or_none(inner_tag, attribute)


def iselect(tag: Tag, selector: str) -> Generator[Tag]:
    """Same as `tag.select(selector)`, but it returns a generator instead of a list."""
    yield from tag.css.iselect(selector)
