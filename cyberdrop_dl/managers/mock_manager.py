from __future__ import annotations

from typing import Any

MOCK_MANAGER = None


class MockCallable:
    def __init__(self, return_obj: Any = None) -> None:
        self.return_obj = return_obj

    def __getitem__(self, parameters: Any) -> object: ...
    def __or__(self, other: Any) -> MockCallable: ...
    def __ror__(self, other: Any) -> MockCallable: ...
    def __call__(self, *args, **kwargs):
        return self.return_obj


class Mock(Any):
    def __init__(self, name: str, /) -> None:
        self._nested_attrs: dict[str, Mock] = {}
        self._mock_name = name

    def __getattribute__(self, name: str, /) -> Any:
        if name == "manager" and MOCK_MANAGER is not None:
            return MOCK_MANAGER
        try:
            return super().__getattribute__(name)
        except AttributeError:
            if name == "_nested_attrs":
                raise  # Avoid infinite recursion
            return self._nested_attrs.get(name, Mock(name))


class MockCacheManager(Mock):
    def __init__(self) -> None:
        self.get = self.save = MockCallable()
        super().__init__("cache_manager")


class MockManager(Mock):
    def __init__(self):
        global MOCK_MANAGER
        assert MOCK_MANAGER is None, "A global MockManager already exists. Only 1 should be created"
        super().__init__("manager")
        self.cache_manager = MockCacheManager()
        MOCK_MANAGER = self


MOCK_MANAGER = MockManager()
