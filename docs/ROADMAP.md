# Roadmap

## Current (v0.1)

- Package `kuvien-parsinta`, CLI `kuvien-parsinta parse <file>`
- **PP-StructureV3** for images and PDFs (layout + OCR, GPU)
- Structure → markdown (text only) + layout PDF (title, photo, columns)
- Multilingual: primary `fi`, fallback langs via `.env`
- Isolated `.venv`, PaddleOCR cloned by `scripts/setup.ps1`

## v0.2

- [x] Hybrid quality pipeline (VL text + StructureV3 layout/bbox/images)
- [x] StructureV3 for fast/regression runs (`--engine structurev3`)
- [ ] Native PDF text extraction before StructureV3 (text PDFs)
- [ ] Batch folder mode (parse entire job directory)
- [ ] CI workflow (pytest without GPU)

## Decisions

- Standalone repo + isolated `.venv`
- Hybrid pipeline default: VL document understanding + StructureV3 geometry; not mutually exclusive
- `parsittavat/` is local input only (not committed except README)
