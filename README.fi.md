# doclayout-ai

> Suomenkielinen README. English version: [README.md](README.md)

**AI-avusteinen dokumenttilayoutin parsinta:** kuvat ja PDF:t → **rakenteinen Markdown + structural PDF**.

**Hybrid Quality Pipeline:** PaddleOCR-VL vastaa tekstistä, lukujärjestyksestä ja kappalejaosta. PP-StructureV3 vastaa layoutista, bboxeista, kuvista ja PDF-geometriasta.

| | |
|---|---|
| **Repo** | [github.com/FoxRav/doclayout-ai](https://github.com/FoxRav/doclayout-ai) |
| **Helppo aloitus** | [`README-Dummies.md`](README-Dummies.md) |
| **Asennus** | [`docs/SETUP.md`](docs/SETUP.md) |
| **Tunnetut virheet & opit** | [`docs/ERRORS.md`](docs/ERRORS.md) |
| **Kielet** | Ensisijaisesti **suomi**; myös ruotsi, englanti ja muut PaddleOCR-kielet |
| **Testit** | `pytest tests/` — unit + regressio |

---

## Mitä työkalu tekee

doclayout-ai muuntaa kuvia ja PDF-tiedostoja kahteen päätulosteeseen:

* rakenteinen Markdown
* uudelleenrakennettu structural PDF

Työkalu ei kopioi koko skannausta PDF:n taustakuvaksi. Se tunnistaa dokumentin rakenteen, tekstilohkot, kuvat, otsikot, lukujärjestyksen ja layoutin, ja rakentaa tulosteen uudelleen.

```text
kuva tai PDF
    → hybrid parser: PaddleOCR-VL + PP-StructureV3
    → PageModel / layout model
    → final text cleanup
    → markdown + structural PDF
    → quality report
```

### Periaatteet

| Sääntö | Toteutus |
|--------|----------|
| Tekstialueet **PDF-tekstinä** | Otsikot, meta, body, caption — ei raster-croppeja tekstille |
| Vain **valokuvat** kuvacropina | Pääkuva / photo block — ei tekstialueita rasterina |
| Markdown **PageModelista** | Ei suoraan raaka-OCR:stä; final-text cleanup ennen tulostetta |
| Ei facsimileä oletuksena | Facsimile vain `--emit-facsimile` → `ocr/<nimi>_facsimile.pdf` |
| Laadunvalvonta | Quality gate: `PASS` / `PASS_WITH_WARNINGS` / `FAIL` |

---

## Tulostiedostot

### Pääkansio (sama kuin syöte)

| Tiedosto | Milloin | Sisältö |
|----------|---------|---------|
| `<nimi>.md` | Aina | Päämarkdown — UTF-8 BOM, rakenteinen teksti PageModelista |
| `<nimi>_structural.pdf` | Oletus (`--pdf-mode structural`) | Uudelleenrakennettu sivu: typografia ja layout |
| `<nimi>_photo.jpg` | Kun StructureV3 löytää `image`-lohkon | Rajattu valokuva |
| `<nimi>_clean.pdf` | Vain `--emit-clean` | Reflowattu teksti-PDF |
| `<nimi>_vl.md` | Hybrid/best | VL:n raakamarkdown (vertailu) |

**Juureen ei kirjoiteta:** `*_test.pdf`, `*_facsimile*.pdf` (facsimile → `ocr/`).

### `ocr/`-kansio (QA & debug)

| Tiedosto | Sisältö |
|----------|---------|
| `<nimi>_vl_res.json` | PaddleOCR-VL raaka |
| `<nimi>_structurev3_res.json` | PP-StructureV3 raaka (hybrid/best) |
| `<nimi>_res.json` | StructureV3 (vain `--engine structurev3`) |
| `<nimi>_hybrid_res.json` | Yhdistetty hybrid-tulos |
| `<nimi>_compare_report.json` | VL vs StructureV3 -erot (best) |
| `<nimi>_layout_debug.jpg` | Bbox-visualisointi lähteestä |
| `<nimi>_page_model.json` | PageModel debug |
| `<nimi>_structural_report.json` | Render-raportti |
| `<nimi>_style_debug.json` | Typografia ja font-roolit |
| `<nimi>_visual_metrics.json` | Layout-mittarit (gap, whitespace, fontit) |
| `<nimi>_source_alignment_metrics.json` | Lähde vs renderöity suhteet |
| `<nimi>_content_audit.json` | Sisältöauditointi |
| `<nimi>_quality_report.json` | Quality gate -tarkistukset |
| `<nimi>_search_text.txt` | Hakukelpoinen tekstikerros (debug) |
| `<nimi>_facsimile.pdf` | Vain `--emit-facsimile` |
| `<nimi>_ocr_overlay_debug.pdf` | Vain `--debug-pdf` |

Raaka-OCR JSON **ei** mene suoraan lopulliseen `.md`:ään.

### Final text cleanup

Moduuli `src/kuvien_parsinta/text/final_text_cleanup.py` — **vain final markdown + PDF-teksti**, ei raaka-OCR:ää:

- Unicode replacement / control -merkit pois
- Pehmeät tavutusmerkit ja rivikatko-tavutukset
- Literaalikorjaukset tunnetuille OCR-virheille

### Quality gate

CLI tulostaa ajon jälkeen:

| Tulos | Merkitys |
|-------|----------|
| `QUALITY: PASS` | Sisältö, layout, typografia, cleanup ja visuaaliset metriikat OK |
| `QUALITY: PASS_WITH_WARNINGS` | Sisältö ehjä, visuaalinen viimeistely vaatii vielä säätöä |
| `QUALITY: FAIL` | Sisällön puute, teksticrop, layout-kova virhe tai fonttikoko alle rajan |

Tarkistukset: content audit, layout-zonit, visual metrics, text cleanup, crop policy.

Yksityiskohdat: [`docs/ERRORS.md`](docs/ERRORS.md).

---

## Käyttöesimerkki

```powershell
kuvien-parsinta parse parsittavat\example\document.jpg --engine hybrid --quality max
```

Tulosteet:

```text
document.md
document_structural.pdf
ocr/document_quality_report.json
```

---

## Pikakäynnistys

```powershell
git clone https://github.com/FoxRav/doclayout-ai.git
cd doclayout-ai
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

.\scripts\activate.ps1
pip install -e ".[dev,pdf]"

kuvien-parsinta parse parsittavat\example\document.jpg
pytest tests/ -q
```

**Syötteet:** [`parsittavat/`](parsittavat/) — paikallinen syötekansio (ei commitoida; vain `.gitkeep` repossa).

**Tuloste:** sama kansio kuin syöte + `ocr/`-alikansio.

---

## CLI

```
kuvien-parsinta parse <tiedosto> [OPTIONS]
kuvien-parsinta languages
```

```powershell
kuvien-parsinta parse <tiedosto> `
  [--engine hybrid|vl|structurev3|best|auto] `
  [--quality standard|max] `
  [--pdf-mode structural|clean|facsimile|all] `
  [--mode auto|flowing|structural] `
  [--out-dir DIR] `
  [--emit-facsimile] [--emit-clean] [--debug-pdf] `
  [--no-pdf]
```

| `--engine` | Käyttö |
|------------|--------|
| `hybrid` | **Oletus** — VL teksti + StructureV3 layout/bbox/kuvat |
| `vl` | Vain PaddleOCR-VL |
| `structurev3` | Vain PP-StructureV3 |
| `best` | Hybrid + vertailuraportti + erilliset raakadatat |

| `--quality` | Käyttö |
|-------------|--------|
| `max` | **Oletus** — orientaatio, unwarping, paras tarkkuus |
| `standard` | Nopeampi ajo |

| `--pdf-mode` | Käyttö |
|--------------|--------|
| `structural` | **Oletus** — `<nimi>_structural.pdf` |
| `clean` | Vain `<nimi>_clean.pdf` |
| `facsimile` | Structural; facsimile erikseen |
| `all` | Structural; muut vain `--emit-*` / `--debug-pdf` |

| `--mode` | Käyttö |
|----------|--------|
| `auto` | **Oletus** — dokumenttityypin mukainen tuloste |
| `flowing` | Yksipalstainen teksti |
| `structural` | Pakota palstat ja layout-PDF |

| Flag | Lisätulos |
|------|-----------|
| `--emit-facsimile` | `ocr/<nimi>_facsimile.pdf` |
| `--emit-clean` | `<nimi>_clean.pdf` |
| `--debug-pdf` | `ocr/*_ocr_overlay_debug.pdf`, `ocr/*_search_layer_debug.pdf` |
| `--no-pdf` | Vain markdown |

---

## Konfigurointi (`.env`)

Kaikki muuttujat: etuliite `PARSE_`. Tiedosto `.env` repojuuressa.

### Moottorit & OCR

| Muuttuja | Oletus | Merkitys |
|----------|--------|----------|
| `PARSE_ENGINE` | `hybrid` | Oletusmoottori |
| `PARSE_QUALITY` | `max` | `standard` \| `max` |
| `PARSE_USE_VL_FOR_TEXT` | `true` | Markdown-teksti VL:stä |
| `PARSE_USE_VL_FOR_READING_ORDER` | `true` | Lukujärjestys VL:stä |
| `PARSE_USE_STRUCTUREV3_FOR_LAYOUT` | `true` | Bbox/palstat StructureV3:sta |
| `PARSE_USE_STRUCTUREV3_FOR_IMAGES` | `true` | Kuvien rajaus |
| `PARSE_USE_STRUCTUREV3_FOR_PDF_GEOMETRY` | `true` | PDF-sivukoko |
| `PARSE_NO_SILENT_FALLBACK` | `true` | Fallback logitetaan |
| `PARSE_VL_PIPELINE_VERSION` | `v1.6` | VL-pipeline |
| `PARSE_VL_DEVICE` | `auto` | VL-laitteisto |
| `PARSE_OCR_DEVICE` | `auto` | StructureV3-laitteisto |
| `PARSE_OCR_PRIMARY_LANGUAGE` | `fi` | Ensisijainen kieli |
| `PARSE_OCR_EXTRA_LANGUAGES` | `sv,en,de,…` | Fallback-järjestys |

### PDF & tuloste

| Muuttuja | Oletus | Merkitys |
|----------|--------|----------|
| `PARSE_PDF_MODE` | `structural` | Pää-PDF-tyyppi |
| `PARSE_WRITE_PDF` | `true` | Generoi PDF |
| `PARSE_EMIT_FACSIMILE` | `false` | Facsimile vain erikseen |
| `PARSE_EMIT_CLEAN` | `false` | Clean-PDF vain erikseen |
| `PARSE_EMIT_DEBUG_PDF` | `false` | Debug-PDF:t |
| `PARSE_DEBUG_OUTPUT_DIR` | `ocr` | QA-kansio syötteen alla |

### Structural layout

| Muuttuja | Oletus | Merkitys |
|----------|--------|----------|
| `PARSE_RENDER_TEXT_AS_IMAGE` | `false` | Teksti renderöidään PDF-tekstinä, ei kuvana |
| `PARSE_ALLOW_TEXT_CROPS` | `false` | Tekstialueiden raster-crop kielletty |
| `PARSE_ALLOW_PHOTO_CROPS` | `true` | Valokuvien crop sallittu |
| `PARSE_LAYOUT_PRESERVE` | `true` | Pyritään säilyttämään lähteen layout |
| `PARSE_NEWSPAPER_COMPACT` | `true` | Tiivis structural layout (pystysuuntainen spacing) |
| `PARSE_BOTTOM_COLUMN_MIN_FONT_SIZE` | `5.5` | Palstatekstin min-fontti |
| `PARSE_BODY_MIN_FONT_SIZE` | `6.0` | Leipätekstin min-fontti |

CUDA-päivitys: `scripts\install_cuda.ps1`

**Huom.** Suomen StructureV3-OCR käyttää latin-mallia ruotsin (`sv`) kautta — PaddleOCR ei tarjoa erillistä `fi`-koodia Structure-pipelineen.

---

## Hybrid Quality Pipeline

| Rooli | PaddleOCR-VL | PP-StructureV3 |
|-------|--------------|----------------|
| **Vastuu** | Teksti, otsikko, kappalejako, lukujärjestys | Bbox, palstat, kuvat, block types |
| **Raaka-JSON** | `ocr/<nimi>_vl_res.json` | `ocr/<nimi>_structurev3_res.json` |
| **Yhdistetty** | | `ocr/<nimi>_hybrid_res.json` |

Konfliktit → `ocr/<nimi>_compare_report.json`. Teksti ratkaistaan VL:llä, layout StructureV3:lla.

```powershell
kuvien-parsinta parse parsittavat\example\document.jpg
kuvien-parsinta parse parsittavat\example\document.jpg --engine best
kuvien-parsinta parse parsittavat\example\document.jpg --engine structurev3
```

---

## Reporakenne

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
├── parsittavat/          # paikalliset syötteet (ei commitoida)
└── pyproject.toml
```

`.venv/`, `PaddleOCR/` ja `parsittavat/*` (paitsi `.gitkeep`) eivät mene gitiin.

---

## Tila

- [x] Hybrid pipeline (VL + StructureV3)
- [x] Structural PDF: source-anchored layout, typography, compact spacing
- [x] Teksti PDF-tekstinä; valokuvat crop
- [x] Final text cleanup
- [x] Quality gate + debug-raportit (`ocr/`)
- [x] pytest (unit + regressio)
- [ ] Eräkansio / useita tiedostoja kerralla (v0.2)
- [ ] CI ilman GPU:ta

Suunnitelma: [`docs/ROADMAP.md`](docs/ROADMAP.md)
