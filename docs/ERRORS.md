# Known errors and lessons learned

## ERROR-0001: Facsimile treated as primary output

**Problem:** Facsimile PDF (full-page source image + invisible text) was treated as the primary result, even though the user wants a structural PDF rebuilt from layout.

**Fix:** Default output is `<name>_structural.pdf` only. Facsimile requires explicit `--emit-facsimile` and is written under `ocr/`.

---

## ERROR-0002: OCR text drawn as visible white overlay on PDF

**Problem:** OCR bounding-box text was rendered as a visible white overlay on the PDF, making output unreadable.

**Fix:** Structural PDF uses template zones and typed text. OCR bboxes are never drawn directly as visible overlay on the primary PDF.

---

## ERROR-0003: Test PDFs written to user input folder

**Problem:** `*_test.pdf`, `*_search_test.pdf`, and similar debug outputs appeared in the user's source folder during normal runs.

**Fix:** Normal runs write only `<name>.md` and `<name>_structural.pdf` to the input folder root. Debug PDFs require `--debug-pdf` and go under `ocr/`.

---

## ERROR-0004: Markdown missing from normal run

**Problem:** Primary markdown (`.md`) was sometimes skipped or empty in normal parse runs.

**Fix:** Markdown is mandatory output, built from `NewspaperPageModel` for newspaper pages. Pipeline fails if markdown is not written.

---

## ERROR-0005: Structural renderer placed elements in wrong order

**Problem:** The bbox-based structural renderer placed masthead at the bottom, headlines below the hero image, and text blocks scattered according to OCR coordinates.

**Fix:** For `document_type == newspaper_front_page`, use `newspaper_template_renderer.py` with fixed relative zones (masthead → meta → headlines → hero + sidebar → caption → bottom headline → columns).

---

## ERROR-0008: Metadata-strip blocks leaked into story/body text

**Problem:** The price line `1 mk (sis. lvv)` was recognized as metadata but also appeared at the start of the right sidebar and in the markdown body section.

**Root cause:** PageModel did not enforce exclusive block ownership. The same block or text could be assigned to multiple roles.

**Fix:** Added `consumed_blocks` tracking, metadata-strip detector, line-level fingerprint filtering, and quality gate checks that reject metadata in story body.

**Regression test:** `tests/regression/test_metadata_strip_not_in_story_body.py`

---

## ERROR-0009: Structural PDF typography too generic

**Problem:** The structural PDF had correct zones but did not resemble a newspaper front page typographically.

**Root cause:** The renderer used template zones without font roles, weight hierarchy, masthead strategy, dedicated caption rendering, or bottom-column minimum readability.

**Fix:** Added `typography_model`, font role mapping, masthead crop/text strategy, caption renderer, meta-row layout, and bottom-column minimum font size gate.

**Regression test:** `tests/regression/test_newspaper_typography_roles.py`

---

## ERROR-0010: Structural PDF lost main story sidebar and image caption

**Problem:** The structural PDF looked better structurally but dropped essential content: the right sidebar body and the image caption below the hero photo.

**Root cause:** The renderer and quality gate accepted output even when source-detected elements never reached the final PDF. Caption detection relied only on VL block typing; sidebar rendering used an incorrect hero bottom coordinate.

**Fix:** Multi-source caption detection (VL, StructureV3, geometry) with scoring, mandatory sidebar/caption rendering, content-loss quality gate (FAIL), and `HeroPlacement`-based layout.

**Regression test:** `tests/regression/test_newspaper_required_story_elements_rendered.py`

---

## ERROR-0011: Structural PDF passed quality gate despite poor visual layout

**Problem:** The structural PDF passed quality checks even though spacing, masthead overlap, and bottom-column readability did not match a newspaper front page.

**Root cause:** Quality gate verified element presence but not layout ratios, vertical gaps, font sizes, or masthead crop strategy.

**Fix:** Source-anchored rendering from OCR bboxes, compact newspaper spacing, masthead crop by default, `visual_metrics.json`, and visual layout quality gate.

**Regression test:** `tests/regression/test_newspaper_visual_layout_metrics.py`

---

## ERROR-0012: Structural PDF used text regions as image crops

**Problem:** Masthead and newspaper name were cropped from the source scan and embedded as raster images in the structural PDF.

**Root cause:** The renderer allowed a masthead crop strategy even though structural PDFs must render all text as PDF text and only embed actual photos.

**Fix:** Added `crop_policy`, forbid text crops by default, render masthead/newspaper/headlines/meta/caption/continuation as text, allow crops only for photo/illustration roles.

**Regression test:** `tests/regression/test_structural_pdf_text_not_cropped.py`

---

## ERROR-0013: Structural PDF passed quality gate despite content loss and misassignment

**Problem:** The structural PDF passed quality checks even though final output was missing text, contained truncated fragments, and mixed content between roles.

**Root cause:** Quality gate validated layout and element presence but not content segment coverage, PDF/markdown extract checks, forbidden fragments, or cross-role leaks.

**Fix:** Added content audit, required segment coverage, PDF/markdown extract verification, forbidden fragment checks, and separate `content_quality` hard gate.

**Regression test:** `tests/regression/test_newspaper_content_completeness_paukku.py`

---

## ERROR-0014: Structural PDF passed before typography and final text polish

**Problem:** The structural PDF was content-complete but still had OCR hyphenation artifacts, loose vertical spacing, small bottom columns, and a masthead that did not yet resemble a newspaper title treatment.

**Root cause:** The quality gate checked content presence and coarse layout but not final text cleanup, compactness ratios, bottom-column readability, masthead similarity, or source-ratio alignment.

**Fix:** Added `final_text_cleanup`, compactness metrics, masthead text styling with `masthead_similarity_warning`, `source_alignment_metrics.json`, bottom-column readability gate, and `PASS_WITH_WARNINGS` when visual finishing is incomplete.

**Regression test:** `tests/regression/test_final_text_cleanup_and_visual_warnings.py`

---

## ERROR-0006: Markdown built directly from raw OCR

**Problem:** Markdown was assembled from raw OCR block order, preserving wrong heading levels and OCR typos in the primary output.

**Fix:** Markdown is generated from `NewspaperPageModel` with `normalize_ocr_text()` applied. Raw OCR JSON is never written to the final `.md`.
