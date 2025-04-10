from typing import Any

root_manager = None


class Mock(Any):
    def __init__(self, name: str):
        self._nested_attrs: dict[str, Mock] = {}
        self._mock_name = name

    def __getattribute__(self, name: str) -> Any:
        if name == "manager" and root_manager is not None:
            return root_manager
        try:
            return super().__getattribute__(name)
        except AttributeError:
            if name == "_nested_attrs":
                raise  # Avoid infinite recursion
            return self._nested_attrs.get(name, Mock(name))

    def __call__(self, *_, **__):
        return self


class MockCacheManager(Mock):
    def __init__(self):
        super().__init__("cache_manager")

    def __getattribute__(self, name: str):
        if name in ("get", "save"):
            return lambda _: None
        return super().__getattribute__(name)


class MockManager(Mock):
    def __init__(self):
        global root_manager
        assert root_manager is None, "A global MockManager already exists. Only 1 should be created"
        super().__init__("manager")
        self.cache_manager = MockCacheManager()
        root_manager = self
