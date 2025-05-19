import sys
from pathlib import Path

import pytest

from cyberdrop_dl.main import run
from cyberdrop_dl.ui.program_ui import ProgramUI


@pytest.fixture(autouse=True)
def test_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # This is just to test that cyberdrop is able to run in the current python version
    msg = "main UI started successfully"

    def main_ui(*_) -> None:
        print(msg)

    monkeypatch.setattr(sys, "argv", ["pytest", "--disable-cache"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ProgramUI, "__init__", main_ui)
    run()
    captured = capsys.readouterr()
    output = captured.out
    assert msg in output


def test_async_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["pytest", "--download"])
    monkeypatch.chdir(tmp_path)
    run()
    captured = capsys.readouterr()
    output = captured.out
    assert "Finished downloading. Enjoy :)" in output
