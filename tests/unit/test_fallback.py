from kuvien_parsinta.fallback import should_fallback_to_vl


def test_vl_fallback_low_avg() -> None:
    assert should_fallback_to_vl(
        ocr_confidence_avg=0.5,
        low_confidence_pages=(0,),
        page_count=2,
    )


def test_vl_fallback_ok() -> None:
    assert not should_fallback_to_vl(
        ocr_confidence_avg=0.95,
        low_confidence_pages=(),
        page_count=3,
    )
