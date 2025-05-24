from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def test_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
