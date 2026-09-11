from __future__ import annotations

from typing import Any, final


@final
class nested_itemgetter:  # noqa: N801
    def __init__(self, key: str | int, *keys: str | int) -> None:
        self.keys: tuple[str | int, ...] = key, *keys

    def __call__(self, obj: Any) -> Any:
        path: list[str | int] = []
        for key in self.keys:
            path.append(key)
            try:
                obj = obj[key]
            except (KeyError, TypeError):
                raise KeyError(str(path)) from None

        return obj

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(map(repr, self.keys))})"


@final
class nested_itemsetter:  # noqa: N801
    def __init__(self, key: str, *keys: str) -> None:
        self.keys = key, *keys
        self._lead_keys = self.keys[:-1]
        self._tail = self.keys[-1]

    __repr__ = nested_itemgetter.__repr__

    def __call__(self, obj: Any, value: Any) -> Any:
        for key in self._lead_keys:
            try:
                obj = obj[key]
            except KeyError:
                obj[key] = {}
                obj = obj[key]

        obj[self._tail] = value
