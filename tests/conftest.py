from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.nodes import Node  # type: ignore


@pytest.fixture
def unique_tmp_dir(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    node: pytest.Function = request.node
    test_name = node.originalname
    num = 0
    test_specific_dir = tmp_path.parent / f"cdl_{test_name}.{num}"
    while test_specific_dir.exists():
        num += 1
        test_specific_dir = test_specific_dir.with_suffix(f".{num}")
        assert num < 5

    test_specific_dir.mkdir(exist_ok=True)
    return test_specific_dir


@pytest.fixture
def tmp_cwd(unique_tmp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(unique_tmp_dir)
    return unique_tmp_dir


@pytest.fixture
def custom_sys_argv(request: pytest.FixtureRequest) -> list[str]:
    args = ["pytest"]
    node: Node = request.node
    if marker := node.get_closest_marker("sys_args"):
        assert marker.args
        assert isinstance(marker.args[0], list)
        return args + marker.args[0]

    return args


@pytest.fixture
async def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(10)
    return caplog
