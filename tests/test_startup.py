import pytest

from cyberdrop_dl.main import run
from cyberdrop_dl.ui.program_ui import ProgramUI


def test_startup(tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # This is just to test that cyberdrop is able to run in the current python version
    msg = "main UI started successfully"

    def main_ui(*_) -> None:
        print(msg)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ProgramUI, "__init__", main_ui)
    run(())
    captured = capsys.readouterr()
    output = captured.out
    assert msg in output


def test_async_startup(tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    run(("--download",))
    captured = capsys.readouterr()
    output = captured.out
    assert "Finished downloading. Enjoy :)" in output
