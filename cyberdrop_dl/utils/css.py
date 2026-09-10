from __future__ import annotations

import dataclasses
import html
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, cast, overload

from cyberdrop_dl.exceptions import ScrapeError

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4.element import Tag

    from cyberdrop_dl.constants import HttpMethod


class SelectorError(ScrapeError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(422, message)


class CssAttributeSelector(NamedTuple):
    element: str
    attribute: str = ""

    def __call__(self, soup: Tag) -> str:
        return select(soup, self.element, self.attribute)

    def text(self, tag: Tag) -> str:
        return select_text(tag, self.element)


@dataclasses.dataclass(slots=True)
class HTMLForm:
    method: HttpMethod
    action: str
    inputs: dict[str, str | None]


class JsonLD(dict[str, Any]):
    @overload
    def __getitem__(self, key: Literal["uploadDate"], /) -> str: ...  # pyright: ignore[reportNoOverloadImplementation]

    @overload
    def __getitem__(self, key: str, /) -> Any:
        """Return self[key]."""

    __getitem__ = dict.__getitem__


def _select_one(tag: Tag, selector: str) -> Tag:
    """Same as `tag.select_one` but asserts the result is not `None`"""
    result = tag.select_one(selector)
    if result is None:
        raise SelectorError(f"{selector} tag not found")
    return result


def select_text(tag: Tag, selector: str, *, strip: bool = True, decompose: str | None = None) -> str:
    """Same as `tag.select_one.get_text(strip=strip)` but asserts the result is not `None`"""
    inner_tag = select(tag, selector)
    if decompose:
        for trash in inner_tag.select(decompose):
            trash.decompose()
    return text(inner_tag, strip=strip)


def attr_or_none(tag: Tag, attribute: str) -> str | None:
    """Same as `tag.get(attribute)` but asserts the result is a single str"""
    attribute_ = attribute
    if attribute_ == "srcset":
        if (srcset := tag.get(attribute_)) and type(srcset) is str:
            return _parse_srcset(srcset)
        attribute_ = "src"

    value = tag.get("data-src") or tag.get(attribute_) if attribute_ == "src" else tag.get(attribute_)
    if value is None:
        return None
    if type(value) is not str:
        raise SelectorError(f"Expected a single value for {attribute = !r}, got multiple")
    return value


def attr(tag: Tag, attribute: str) -> str:
    """Same as `tag.get(attribute)` but asserts the result is not `None` and is a single string"""
    result = attr_or_none(tag, attribute)
    if result is None:
        raise SelectorError(f"{attribute = } not found")
    return result


def text(tag: Tag, *, strip: bool = True) -> str:
    return tag.get_text(strip=strip)


@overload
def select(tag: Tag, selector: str) -> Tag: ...


@overload
def select(tag: Tag, selector: str, attribute: str) -> str: ...


def select(tag: Tag, selector: str, attribute: str | None = None) -> Tag | str:
    inner_tag = _select_one(tag, selector)
    if not attribute:
        return inner_tag
    return attr(inner_tag, attribute)


@overload
def iselect(tag: Tag, selector: str) -> Generator[Tag]: ...


@overload
def iselect(tag: Tag, selector: str, attribute: str) -> Generator[str]: ...


def iselect(tag: Tag, selector: str, attribute: str | None = None) -> Generator[Tag] | Generator[str]:
    """Same as `tag.select(selector)`, but it returns a generator instead of a list."""
    tags = tag.css.iselect(selector)
    if not attribute:
        yield from tags

    else:
        for inner_tag in tags:
            if attr := attr_or_none(inner_tag, attribute):
                yield attr


def iselect_text(soup: Tag, /, selector: str, contains: tuple[str, ...] | str = ()) -> Generator[str]:
    if isinstance(contains, str):
        contains = (contains,)

    for tag in iselect(soup, selector):
        content = text(tag)
        for key in contains:
            if key not in content:
                continue
        yield content


def _parse_srcset(srcset: str) -> str:
    # The best src is the last one (usually)
    return [src.split(" ")[0] for src in srcset.split(", ")][-1]


def decompose(tag: Tag, selector: str) -> None:
    for inner_tag in tag.select(selector):
        inner_tag.decompose()


def rstrip_domain(title: str, domain: str) -> str:
    assert domain
    second_level_domain = domain.rsplit(".", 1)[0].casefold().removeprefix("www.")

    def sanitize(string: str, char: str) -> str:
        front, _, tail = string.rpartition(char)
        if front and second_level_domain in tail.casefold():
            return front.strip()
        return string

    for char in sorted(("|", " - "), key=title.rfind, reverse=True):
        title = sanitize(title, char)

    return title


def page_title(soup: Tag, domain: str | None = None) -> str:
    title = select_text(soup, "title")
    if domain:
        return rstrip_domain(title, domain)
    return title


def parse_form(form: Tag, /) -> HTMLForm:
    inputs: dict[str, str | None] = {}
    for elem in iselect(form, "input"):
        name = attr_or_none(elem, "name") or attr(elem, "id")
        inputs[name] = attr_or_none(elem, "value")

    method = attr(form, "method").upper()
    action = attr(form, "action")
    return HTMLForm(cast("HttpMethod", method), action, inputs)


unescape = html.unescape
iframes = CssAttributeSelector("iframe", "src")
images = CssAttributeSelector("img", "srcset")
links = CssAttributeSelector(":any-link", "href")
