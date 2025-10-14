from pathlib import Path

import pytest

from cyberdrop_dl.main import run
from cyberdrop_dl.ui.program_ui import ProgramUI


def test_startup(tmp_cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # This is just to test that cyberdrop is able to run in the current python version
    msg = "main UI started successfully"

    def main_ui(*_) -> None:
        print(msg)

    monkeypatch.setattr(ProgramUI, "__init__", main_ui)
    run(())
    captured = capsys.readouterr()
    output = captured.out
    assert msg in output


def test_async_startup(tmp_cwd: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(10)
    run(("--download",))
    assert "Finished downloading. Enjoy :)" in caplog.text
