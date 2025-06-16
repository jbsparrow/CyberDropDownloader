from collections.abc import Mapping
from typing import Any


class DotAccesDict(dict):
    def __init__(self, map: Mapping[str, Any] | None = None, **kwargs: Any) -> None:
        if map is None:
            map = {}
        else:
            map = dict(map)
        if kwargs:
            map.update(**kwargs)
        for k, v in map.items():
            setattr(self, k, v)

        for k in self.__class__.__dict__.keys():
            if not (k.startswith("__") and k.endswith("__")) and k not in ("update", "pop"):
                setattr(self, k, getattr(self, k))

    def __setattr__(self, name: str, value: Any) -> None:
        if isinstance(value, list | tuple):
            value = type(value)(self.__class__(x) if isinstance(x, dict) else x for x in value)
        elif isinstance(value, dict) and not isinstance(value, DotAccesDict):
            value = DotAccesDict(value)
        super().__setattr__(name, value)
        super().__setitem__(name, value)

    __setitem__ = __setattr__

    def update(self, map: dict[str, Any] | None = None, /, **kwargs: Any) -> None:
        data = map or {}
        data.update(kwargs)
        for key in data:
            setattr(self, key, data[key])

    def pop(self, k: str, *args) -> Any:
        if hasattr(self, k):
            delattr(self, k)
        return super().pop(k, *args)
