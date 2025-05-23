from cyberdrop_dl.utils.utilities import sanitize_unicode_emojis_and_symbols


def test_sanitize_macos_problematic_unicode_symbol():
    assert sanitize_unicode_emojis_and_symbols("🫧Bubblz🫧") == "Bubblz"


def test_sanitization_must_keep_other_languages_chars():
    assert sanitize_unicode_emojis_and_symbols("これは単なるテストです") == "これは単なるテストです"
    assert sanitize_unicode_emojis_and_symbols("это всего лишь тест") == "это всего лишь тест"
    assert sanitize_unicode_emojis_and_symbols("این فقط یک آزمایش است") == "این فقط یک آزمایش است"
    assert sanitize_unicode_emojis_and_symbols("هذا مجرد اختبار") == "هذا مجرد اختبار"
