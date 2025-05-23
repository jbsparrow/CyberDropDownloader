import os
from pathlib import Path

import pytest

from cyberdrop_dl.utils.utilities import sanitize_filename, sanitize_unicode_emojis_and_symbols

IS_WINDOWS = os.name == "nt"
IS_MACOS = os.name == "darwin"


FOREIGN_LENGUAGE_STRINGS = ["これは単なるテストです", "это всего лишь тест", "این فقط یک آزمایش است", "هذا مجرد اختبار"]
INVALID_UNICODE9_STRING = "🫧Bubblz🫧"


def test_sanitize_macos_problematic_unicode_symbol() -> None:
    assert sanitize_unicode_emojis_and_symbols(INVALID_UNICODE9_STRING) == "Bubblz"


@pytest.mark.parametrize("name", FOREIGN_LENGUAGE_STRINGS)
def test_sanitization_must_keep_other_languages_chars(name: str) -> None:
    assert sanitize_unicode_emojis_and_symbols(name) == name


@pytest.mark.skipif(not (IS_WINDOWS or IS_MACOS))
def test_unicode9_filename_raise_os_error(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        tmp_path.joinpath(INVALID_UNICODE9_STRING).with_suffix(".txt").write_text("OK")


@pytest.mark.parametrize("name", [INVALID_UNICODE9_STRING, *FOREIGN_LENGUAGE_STRINGS])
def test_sanitized_filename_do_not_raise_os_errors(name: str, tmp_path: Path) -> None:
    filename = sanitize_filename(name)
    tmp_path.joinpath(filename).with_suffix(".txt").write_text("OK")
