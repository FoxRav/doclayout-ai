# doclayout-ai

> Finnish README: [README.fi.md](README.fi.md)

**AI-assisted document layout parsing:** images and PDFs → **structured Markdown + structural PDF**.

**Hybrid Quality Pipeline:** PaddleOCR-VL handles text, reading order and paragraph structure. PP-StructureV3 handles layout, bounding boxes, images and PDF geometry.

| | |
|---|---|
| **Repo** | [github.com/FoxRav/doclayout-ai](https://github.com/FoxRav/doclayout-ai) |
| **Quick intro** | [`README-Dummies.md`](README-Dummies.md) |
| **Setup** | [`docs/SETUP.md`](docs/SETUP.md) |
| **Known issues & lessons** | [`docs/ERRORS.md`](docs/ERRORS.md) |
| **Languages** | Primarily **Finnish**; also Swedish, English and other PaddleOCR languages |
| **Tests** | `pytest tests/` — unit + regression |

---

## What the tool does

doclayout-ai converts images and PDF files into two main outputs:

* structured Markdown
* rebuilt structural PDF

The tool does not copy the entire scan as a PDF background image. It detects document structure, text blocks, photos, headings, reading order and layout, then reconstructs the output.

```text
image or PDF
    → hybrid parser: PaddleOCR-VL + PP-StructureV3
    → PageModel / layout model
    → final text cleanup
    → markdown + structural PDF
    → quality report
```

### Principles

| Rule | Implementation |
|------|----------------|
| Text regions rendered as **PDF text** | Headings, meta, body, caption — no raster crops for text |
| **Photos** only as image crops | Main photo / photo block — no text regions as raster |
| Markdown from **PageModel** | Not directly from raw OCR; final-text cleanup before output |
| No facsimile by default | Facsimile only with `--emit-facsimile` → `ocr/<name>_facsimile.pdf` |
| Quality control | Quality gate: `PASS` / `PASS_WITH_WARNINGS` / `FAIL` |

---

## Output files

### Main output directory (same as input)

| File | When | Content |
|------|------|---------|
| `<name>.md` | Always | Primary markdown — UTF-8 BOM, structured text from PageModel |
| `<name>_structural.pdf` | Default (`--pdf-mode structural`) | Rebuilt page: typography and layout |
| `<name>_photo.jpg` | When StructureV3 finds an `image` block | Cropped photo |
| `<name>_clean.pdf` | Only `--emit-clean` | Reflowed text PDF |
| `<name>_vl.md` | Hybrid/best | VL raw markdown (comparison) |

**Not written to repo root:** `*_test.pdf`, `*_facsimile*.pdf` (facsimile → `ocr/`).

### `ocr/` directory (QA & debug)

| File | Content |
|------|---------|
| `<name>_vl_res.json` | PaddleOCR-VL raw output |
| `<name>_structurev3_res.json` | PP-StructureV3 raw output (hybrid/best) |
| `<name>_res.json` | StructureV3 (only `--engine structurev3`) |
| `<name>_hybrid_res.json` | Combined hybrid result |
| `<name>_compare_report.json` | VL vs StructureV3 differences (best) |
| `<name>_layout_debug.jpg` | Bbox visualization from source |
| `<name>_page_model.json` | PageModel debug |
| `<name>_structural_report.json` | Render report |
| `<name>_style_debug.json` | Typography and font roles |
| `<name>_visual_metrics.json` | Layout metrics (gap, whitespace, fonts) |
| `<name>_source_alignment_metrics.json` | Source vs rendered ratios |
| `<name>_content_audit.json` | Content audit |
| `<name>_quality_report.json` | Quality gate checks |
| `<name>_search_text.txt` | Searchable text layer (debug) |
| `<name>_facsimile.pdf` | Only `--emit-facsimile` |
| `<name>_ocr_overlay_debug.pdf` | Only `--debug-pdf` |

Raw OCR JSON is **not** written directly to the final `.md`.

### Final text cleanup

Module `src/kuvien_parsinta/text/final_text_cleanup.py` — **final markdown + PDF text only**, not raw OCR:

- Remove Unicode replacement / control characters
- Soft hyphens and line-break hyphenation
- Literal fixes for known OCR errors

### Quality gate

After each run, the CLI prints:

| Result | Meaning |
|--------|---------|
| `QUALITY: PASS` | Content, layout, typography, cleanup and visual metrics OK |
| `QUALITY: PASS_WITH_WARNINGS` | Content intact; visual polish still needs tuning |
| `QUALITY: FAIL` | Missing content, text crop, hard layout error or font size below threshold |

Checks: content audit, layout zones, visual metrics, text cleanup, crop policy.

Details: [`docs/ERRORS.md`](docs/ERRORS.md).

---

## Usage example

```powershell
kuvien-parsinta parse parsittavat\example\document.jpg --engine hybrid --quality max
```

Output:

```text
document.md
document_structural.pdf
ocr/document_quality_report.json
```

---

## Quick start

```powershell
git clone https://github.com/FoxRav/doclayout-ai.git
cd doclayout-ai
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

.\scripts\activate.ps1
pip install -e ".[dev,pdf]"

kuvien-parsinta parse parsittavat\example\document.jpg
pytest tests/ -q
```

**Input:** [`parsittavat/`](parsittavat/) — local input directory (not committed to Git; only `.gitkeep` in the repo).

**Output:** same directory as input + `ocr/` subdirectory.

---

## CLI

```
kuvien-parsinta parse <file> [OPTIONS]
kuvien-parsinta languages
```

```powershell
kuvien-parsinta parse <file> `
  [--engine hybrid|vl|structurev3|best|auto] `
  [--quality standard|max] `
  [--pdf-mode structural|clean|facsimile|all] `
  [--mode auto|flowing|structural] `
  [--out-dir DIR] `
  [--emit-facsimile] [--emit-clean] [--debug-pdf] `
  [--no-pdf]
```

| `--engine` | Usage |
|------------|-------|
| `hybrid` | **Default** — VL text + StructureV3 layout/bbox/photos |
| `vl` | PaddleOCR-VL only |
| `structurev3` | PP-StructureV3 only |
| `best` | Hybrid + comparison report + separate raw outputs |

| `--quality` | Usage |
|-------------|-------|
| `max` | **Default** — orientation, unwarping, best accuracy |
| `standard` | Faster run |

| `--pdf-mode` | Usage |
|--------------|-------|
| `structural` | **Default** — `<name>_structural.pdf` |
| `clean` | Only `<name>_clean.pdf` |
| `facsimile` | Structural; facsimile separately |
| `all` | Structural; others only via `--emit-*` / `--debug-pdf` |

| `--mode` | Usage |
|----------|-------|
| `auto` | **Default** — output follows document type |
| `flowing` | Single-column text |
| `structural` | Force columns and layout PDF |

| Flag | Extra output |
|------|--------------|
| `--emit-facsimile` | `ocr/<name>_facsimile.pdf` |
| `--emit-clean` | `<name>_clean.pdf` |
| `--debug-pdf` | `ocr/*_ocr_overlay_debug.pdf`, `ocr/*_search_layer_debug.pdf` |
| `--no-pdf` | Markdown only |

---

## Configuration (`.env`)

All variables use the `PARSE_` prefix. Place `.env` in the repo root.

### Engines & OCR

| Variable | Default | Meaning |
|----------|---------|---------|
| `PARSE_ENGINE` | `hybrid` | Default engine |
| `PARSE_QUALITY` | `max` | `standard` \| `max` |
| `PARSE_USE_VL_FOR_TEXT` | `true` | Markdown text from VL |
| `PARSE_USE_VL_FOR_READING_ORDER` | `true` | Reading order from VL |
| `PARSE_USE_STRUCTUREV3_FOR_LAYOUT` | `true` | Bbox/columns from StructureV3 |
| `PARSE_USE_STRUCTUREV3_FOR_IMAGES` | `true` | Photo cropping |
| `PARSE_USE_STRUCTUREV3_FOR_PDF_GEOMETRY` | `true` | PDF page size |
| `PARSE_NO_SILENT_FALLBACK` | `true` | Fallback is logged |
| `PARSE_VL_PIPELINE_VERSION` | `v1.6` | VL pipeline |
| `PARSE_VL_DEVICE` | `auto` | VL device |
| `PARSE_OCR_DEVICE` | `auto` | StructureV3 device |
| `PARSE_OCR_PRIMARY_LANGUAGE` | `fi` | Primary language |
| `PARSE_OCR_EXTRA_LANGUAGES` | `sv,en,de,…` | Fallback order |

### PDF & output

| Variable | Default | Meaning |
|----------|---------|---------|
| `PARSE_PDF_MODE` | `structural` | Primary PDF type |
| `PARSE_WRITE_PDF` | `true` | Generate PDF |
| `PARSE_EMIT_FACSIMILE` | `false` | Facsimile only when requested |
| `PARSE_EMIT_CLEAN` | `false` | Clean PDF only when requested |
| `PARSE_EMIT_DEBUG_PDF` | `false` | Debug PDFs |
| `PARSE_DEBUG_OUTPUT_DIR` | `ocr` | QA directory under input |

### Structural layout

| Variable | Default | Meaning |
|----------|---------|---------|
| `PARSE_RENDER_TEXT_AS_IMAGE` | `false` | Text rendered as PDF text, not as image |
| `PARSE_ALLOW_TEXT_CROPS` | `false` | Raster crop of text regions disabled |
| `PARSE_ALLOW_PHOTO_CROPS` | `true` | Photo crops allowed |
| `PARSE_LAYOUT_PRESERVE` | `true` | Preserve source layout where possible |
| `PARSE_NEWSPAPER_COMPACT` | `true` | Compact structural layout (vertical spacing) |
| `PARSE_BOTTOM_COLUMN_MIN_FONT_SIZE` | `5.5` | Column text minimum font size |
| `PARSE_BODY_MIN_FONT_SIZE` | `6.0` | Body text minimum font size |

CUDA update: `scripts\install_cuda.ps1`

**Note.** Finnish StructureV3 OCR uses the Latin model via Swedish (`sv`) — PaddleOCR does not provide a separate `fi` code for the Structure pipeline.

---

## Hybrid Quality Pipeline

| Role | PaddleOCR-VL | PP-StructureV3 |
|------|--------------|----------------|
| **Responsibility** | Text, headings, paragraph structure, reading order | Bbox, columns, photos, block types |
| **Raw JSON** | `ocr/<name>_vl_res.json` | `ocr/<name>_structurev3_res.json` |
| **Combined** | | `ocr/<name>_hybrid_res.json` |

Conflicts → `ocr/<name>_compare_report.json`. Text resolved by VL, layout by StructureV3.

```powershell
kuvien-parsinta parse parsittavat\example\document.jpg
kuvien-parsinta parse parsittavat\example\document.jpg --engine best
kuvien-parsinta parse parsittavat\example\document.jpg --engine structurev3
```

---

## Repository structure

```
├── src/kuvien_parsinta/
│   ├── cli.py, pipeline.py
│   ├── engines/          # VL, StructureV3, hybrid
│   ├── layout/           # PageLayout, PageModel, typography
│   ├── text/             # content assembly, final_text_cleanup
│   ├── pdf/              # structural renderer, facsimile
│   └── quality/          # content audit, visual metrics, quality gate
├── tests/
│   ├── unit/
│   └── regression/
├── scripts/
├── docs/
├── parsittavat/          # local inputs (not committed to Git)
└── pyproject.toml
```

`.venv/`, `PaddleOCR/` and `parsittavat/*` (except `.gitkeep`) are not tracked by Git.

---

## Status

- [x] Hybrid pipeline (VL + StructureV3)
- [x] Structural PDF: source-anchored layout, typography, compact spacing
- [x] Text as PDF text; photos as crops
- [x] Final text cleanup
- [x] Quality gate + debug reports (`ocr/`)
- [x] pytest (unit + regression)
- [ ] Batch folder / multiple files at once (v0.2)
- [ ] CI without GPU

Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)
