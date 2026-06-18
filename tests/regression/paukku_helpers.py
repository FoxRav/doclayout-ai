"""Shared helpers for paukku newspaper regression tests."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.layout.newspaper_page_model import (
    NewspaperFrontPageModel,
    build_newspaper_page_model,
)
from kuvien_parsinta.layout.page_layout import PageLayout
from kuvien_parsinta.text.final_text_cleanup import apply_cleanup_to_page_model
from kuvien_parsinta.text.newspaper_content_assembly import assemble_newspaper_page_model_content


def build_assembled_paukku_model(
    *,
    layout: PageLayout,
    image: Path,
    structure: Path,
    vl: Path | None,
    tmp_dir: Path,
) -> NewspaperFrontPageModel:
    model = build_newspaper_page_model(
        layout=layout,
        source_path=image,
        vl_json_path=vl if vl is not None and vl.is_file() else None,
        structure_json_path=structure,
        tmp_dir=tmp_dir,
    )
    return apply_cleanup_to_page_model(
        assemble_newspaper_page_model_content(
            model,
            vl_json_path=vl if vl is not None and vl.is_file() else None,
            structure_json_path=structure,
            page_width_px=layout.page_width_px,
            page_height_px=layout.page_height_px,
        )
    )
