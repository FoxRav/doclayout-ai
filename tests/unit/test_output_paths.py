"""Tests for output path resolution."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.output_paths import resolve_output_dir


def test_resolve_output_dir_defaults_to_source_parent(tmp_path: Path) -> None:
    source = tmp_path / "Kuulutus" / "kuulutus.jpg"
    source.parent.mkdir()
    source.touch()
    assert resolve_output_dir(source.resolve()) == source.parent.resolve()


def test_resolve_output_dir_explicit_override(tmp_path: Path) -> None:
    source = tmp_path / "in" / "doc.png"
    source.parent.mkdir(parents=True)
    source.touch()
    custom = tmp_path / "custom-out"
    assert resolve_output_dir(source.resolve(), custom) == custom.resolve()
