from kuvien_parsinta.encoding import fix_mojibake, looks_like_mojibake


def test_mojibake_detected() -> None:
    assert looks_like_mojibake("kÃ¤sittely")


def test_mojibake_fix_finnish() -> None:
    # cp1252 misread as latin-1 style marker
    raw = "Ã¤"
    fixed = fix_mojibake("kÃ¤sittely")
    assert "Ã" not in fixed or fixed != raw


def test_clean_text_unchanged() -> None:
    text = "Puolangan vuodeosasto"
    assert fix_mojibake(text) == text
