"""OCR text corrections applied only to final markdown and PDF output."""

from __future__ import annotations

# Known OCR errors for Finnish newspaper text (applied to final output only).
_OCR_CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("ERISTETTHIN", "ERISTETTIIN"),
    ("kasvol", "kasvoi"),
    ("rajahdys", "räjähdys"),
    ("rajjahdyksen", "räjähdyksen"),
    ("saasmista", "saamista"),
    ("hältys", "hälytys"),
    ("polliiasemalle", "poliisiasemalle"),
    ("kaakseksi", "kaaokseksi"),
    ("heinkilöä", "henkilöä"),
    ("Lapuailla", "Lapualla"),
    ("pelastushenkölökunnalta", "pelastushenkilökunnalta"),
    ("vapaehtoiset", "vapaaehtoiset"),
    ("kookontui", "kokoontui"),
    ("TISTAINA", "TIISTAINA"),
    ("Vilmeisimpien", "Viimeisimpien"),
    ("Vilmeisimplen", "Viimeisimpien"),
    ("johtimmm", "johti mm."),
    ("En-simmäinen", "Ensimmäinen"),
    ("on-nettomuudesta", "onnettomuudesta"),
    ("räjähdyspalkalle", "räjähdyspaikalle"),
    ("keskusairalaaan", "keskussairaalaan"),
    ("irroitettavissa", "irrotettavissa"),
)


def normalize_ocr_text(text: str) -> str:
    """Apply known OCR corrections to final output text."""
    result = text
    for wrong, correct in _OCR_CORRECTIONS:
        result = result.replace(wrong, correct)
        if wrong != wrong.upper():
            result = result.replace(wrong.upper(), correct.upper())
    return result
