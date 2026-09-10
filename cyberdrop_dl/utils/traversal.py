from __future__ import annotations

import contextlib
from collections.abc import Callable, Generator, Mapping
from typing import Any, TypeGuard, overload

from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.signature import simple_repr

type Path = tuple[str | int, ...]
type Validator = Callable[[object], bool]


@overload
def traverse[T](
    value: object, visitor: Callable[[Path, Any], TypeGuard[T]], path: Path = ()
) -> Generator[tuple[Path, T]]: ...


@overload
def traverse(value: object, visitor: Callable[[Path, Any], bool], path: Path = ()) -> Generator[tuple[Path, Any]]: ...


def traverse(value: object, visitor: Callable[[Path, Any], Any], path: Path = ()) -> Generator[tuple[Path, Any]]:
    if visitor(path, value):
        yield path, value
        return

    match value:
        case dict():
            for key, item in value.items():
                yield from traverse(item, visitor, (*path, key))

        case list() | tuple():
            for index, item in enumerate(value):
                yield from traverse(item, visitor, (*path, index))

        case _:
            pass


@contextlib.contextmanager
def catch[T](name: str | None = None) -> Generator[None]:
    try:
        yield
    except StopIteration:
        raise ScrapeError(422, f"Unable to find {name}" if name else None) from None


def is_class_info(obj: object) -> TypeGuard[type | tuple[type, ...]]:
    return isinstance(obj, type) or (isinstance(obj, tuple) and all(isinstance(val, type) for val in obj))


def cast_validator(obj: object) -> Validator:
    if obj is ...:
        return lambda _: True
    if is_class_info(obj):
        return lambda x: isinstance(x, obj)

    return lambda x: x == obj


class DictVisitor:
    def __init__(self, keys: tuple[str, ...], validate: Mapping[str, Any] | None = None) -> None:
        validate = validate or {}
        self.target_keys: set[str] = set(validate).union(keys)
        self.validators: dict[str, Validator] = {key: cast_validator(value) for key, value in validate.items()}

    __repr__ = simple_repr("target_keys", "validators")

    def __call__(self, path: Path, obj: object) -> TypeGuard[dict[str, Any]]:  # noqa: ARG002
        if not (isinstance(obj, dict) and self.target_keys.issubset(obj)):
            return False

        return all(validator(obj[name]) for name, validator in self.validators.items())


def find_objs(
    value: object, *keys: str, validate: Mapping[str, Any] | None = None
) -> Generator[tuple[Path, dict[str, Any]]]:
    return traverse(value, DictVisitor(keys, validate))


def find_obj(value: object, *keys: str, validate: Mapping[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
    visitor = DictVisitor(keys, validate)
    with catch(f"object with keys = {sorted(visitor.target_keys)}"):
        return next(iter(traverse(value, visitor)))
