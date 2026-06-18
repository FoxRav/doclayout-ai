from kuvien_parsinta.languages import merge_language_priority, paddle_lang_for_attempt


def test_language_priority_dedup() -> None:
    p = merge_language_priority(primary="fi", extra=("sv", "en", "fi"))
    assert p == ("fi", "sv", "en")


def test_paddle_lang_fallback_latin() -> None:
    assert paddle_lang_for_attempt(attempt_index=99, priority=("fi", "en")) == "latin"
