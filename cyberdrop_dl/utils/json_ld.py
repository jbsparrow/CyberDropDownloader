from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal, overload

from cyberdrop_dl.utils import css, dates, traversal

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from bs4.element import Tag


def _find(
    soup: Tag, keys: tuple[str, ...], validate: Mapping[str, Any] | None = None
) -> tuple[tuple[Any, ...], traversal.DictVisitor]:
    visitor = traversal.DictVisitor(keys, validate)
    json_lds = tuple(iselect(soup, tuple(visitor.target_keys)))
    return json_lds, visitor


def ifind(
    soup: Tag, *keys: str, validate: Mapping[str, Any] | None = None
) -> Iterable[tuple[traversal.Path, dict[str, Any]]]:
    json_lds, visitor = _find(soup, keys, validate)
    return traversal.traverse(json_lds, visitor)


def find(soup: Tag, *keys: str, validate: Mapping[str, Any] | None = None) -> tuple[traversal.Path, dict[str, Any]]:
    json_lds, visitor = _find(soup, keys, validate)
    try:
        return next(traversal.traverse(json_lds, visitor))
    except StopIteration:
        contains = tuple(sorted(visitor.target_keys))
        details = f" with keys {contains}" if contains else ""
        raise css.SelectorError(f"ld-json{details} not found") from None


def find_elem(soup: Tag, type: str, *keys: str) -> dict[str, Any]:  # noqa: A002
    return find(soup, type, *keys)[1]


@overload
def find_attr(
    soup: Tag, attr: Literal["uploadDate", "datePublished"], *keys: str, validate: Mapping[str, Any] | None = None
) -> str: ...


@overload
def find_attr(soup: Tag, attr: str, *keys: str, validate: Mapping[str, Any] | None = None) -> Any: ...


def find_attr(soup: Tag, attr: str, *keys: str, validate: Mapping[str, Any] | None = None) -> Any:
    _, obj = find(soup, attr, *keys, validate=validate)
    return obj[attr]


def upload_date(soup: Tag, *keys: str, validate: Mapping[str, Any] | None = None) -> float:
    return dates.parse_iso(find_attr(soup, "uploadDate", *keys, validate=validate)).timestamp()


def date_published(soup: Tag, *keys: str, validate: Mapping[str, Any] | None = None) -> float:
    return dates.parse_iso(find_attr(soup, "datePublished", *keys, validate=validate)).timestamp()


def iselect(soup: Tag, /, contains: tuple[str, ...] | str = ()) -> Iterable[Any]:
    return map(json.loads, css.iselect_text(soup, "script[type='application/ld+json']", contains))
