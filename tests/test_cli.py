import sys

import pytest

from cyberdrop_dl.main import run


def test_help(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # This is just to test that cyberdrop is able to run in the current python version
    monkeypatch.setattr(sys, "argv", ["pytest", "--help"])
    try:
        run()
    except SystemExit:
        pass
    captured = capsys.readouterr()
    output = captured.out
    assert "Bulk asynchronous downloader for multiple file hosts" in output
