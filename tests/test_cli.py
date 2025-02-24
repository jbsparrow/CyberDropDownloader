import sys

import pytest

from cyberdrop_dl.main import main


def test_help(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    # This is just to test that cyberdrop is able to run in the current python version
    monkeypatch.setattr(sys, "argv", ["pytest", "--help"])
    main(profiling=True, ask=False)
    captured = capsys.readouterr()
    output = captured.out
    assert "Bulk asynchronous downloader for multiple file hosts" in output
