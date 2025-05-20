import pytest

from cyberdrop_dl.main import run
from cyberdrop_dl.ui.program_ui import ProgramUI


def test_startup(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # This is just to test that cyberdrop is able to run in the current python version
    msg = "main UI started successfully"

    def main_ui(*_) -> None:
        print(msg)

    monkeypatch.setattr("sys.argv", ["pytest", "--disable-cache"])
    monkeypatch.setattr(ProgramUI, "__init__", main_ui)
    run()
    captured = capsys.readouterr()
    output = captured.out
    assert msg in output


def test_async_startup(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["pytest", "--download"])
    run()
    captured = capsys.readouterr()
    output = captured.out
    assert "Finished downloading. Enjoy :)" in output
