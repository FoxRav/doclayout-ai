# doclayout-ai

**Monikielinen asiakirjojen parsinta:** valokuvat ja PDF:t → **rakenteinen markdown + structural PDF**.

**Hybrid Quality Pipeline:** PaddleOCR-VL (teksti, lukujärjestys, kappalejako) + PP-StructureV3 (layout, bbox, kuvat, PDF-geometria).

| | |
|---|---|
| **Repo** | [github.com/FoxRav/doclayout-ai](https://github.com/FoxRav/doclayout-ai) |
| **Helppo aloitus** | [`README-Dummies.md`](README-Dummies.md) |
| **Asennus** | [`docs/SETUP.md`](docs/SETUP.md) |
| **Tunnetut virheet & opit** | [`docs/ERRORS.md`](docs/ERRORS.md) |
| **Kielet** | Ensisijaisesti **suomi**; myös ruotsi, englanti ja muut PaddleOCR-kielet |
| **Testit** | `pytest tests/` — 80 testiä (unit + regressio) |

---

## Mitä työkalu tekee

Työkalu **ei kopioi koko skannausta** PDF:ään. Se tunnistaa rakenteen ja **rakentaa uudelleen**:

- **Yksipalstaiset asiakirjat** (kuulutukset, yksinkertaiset lehtileikkeet) → flowing markdown + layout-PDF
- **Sanomalehden etusivu** (`document_type == newspaper_front_page`) → `NewspaperPageModel` → typografioitu **structural PDF** + siisti markdown

```
kuva (jpg/png) tai PDF
    → hybrid (oletus): PaddleOCR-VL + PP-StructureV3
    → yhdistetty markdown + structural PDF
    → tai yksittäinen moottori: --engine vl | structurev3 | best
```

### Periaatteet (sanomalehti)

| Sääntö | Toteutus |
|--------|----------|
| Tekstialueet **PDF-tekstinä** | Masthead, otsikot, meta, sidebar, caption, alapalstat — ei raster-croppeja |
| Vain **valokuvat** kuvacropina | Hero-kuva (ja vastaavat photo-roolit) |
| Markdown **PageModelista** | Ei suoraan raaka-OCR:stä; final-text cleanup ennen tulostetta |
| Ei facsimileä oletuksena | Facsimile vain `--emit-facsimile` → `ocr/<nimi>_facsimile.pdf` |
| Laadunvalvonta | Automaattinen quality gate sanomalehdille (`PASS` / `PASS_WITH_WARNINGS` / `FAIL`) |

---

## Tulostiedostot

### Pääkansio (sama kuin syöte)

| Tiedosto | Milloin | Sisältö |
|----------|---------|---------|
| `<nimi>.md` | Aina | **Päämarkdown** — UTF-8 BOM; sanomalehdellä rakenteinen teksti PageModelista |
| `<nimi>_structural.pdf` | Oletus (`--pdf-mode structural`) | Uudelleenrakennettu sivu: typografia, layout, hero-kuva |
| `<nimi>.pdf` | Legacy-alias / yksinkertainen layout | Koivisto-tyyppiset lehtileikkeet (ei sanomalehden pääpolku) |
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
| `<nimi>_page_model.json` | `NewspaperFrontPageModel` debug |
| `<nimi>_structural_report.json` | Render-raportti (sidebar, caption, sarakkeet) |
| `<nimi>_style_debug.json` | Fontit, roolit, `masthead_similarity_warning` |
| `<nimi>_visual_metrics.json` | Tiiviys, gap-ratio, whitespace, font-koot |
| `<nimi>_source_alignment_metrics.json` | Lähde vs renderöity suhteet |
| `<nimi>_content_audit.json` | Segmenttien kattavuus (A–H) |
| `<nimi>_quality_report.json` | Kaikki quality gate -tarkistukset |
| `<nimi>_search_text.txt` | Hakukelpoinen tekstikerros (debug) |
| `<nimi>_facsimile.pdf` | Vain `--emit-facsimile` |
| `<nimi>_ocr_overlay_debug.pdf` | Vain `--debug-pdf` |

Raaka-OCR JSON **ei** mene suoraan lopulliseen `.md`:ään.

---

## Sanomalehden structural PDF — putki

```
StructureV3 + VL bboxes
    → PageLayout (block types: masthead, headline, hero, sidebar, …)
    → NewspaperFrontPageModel (exclusive block ownership)
    → newspaper_content_assembly (sidebar 2 kpl, caption, meta)
    → final_text_cleanup (tavutukset, kontrollimerkit, literaalikorjaukset)
    → newspaper_template_renderer (source-anchored layout + typography)
    → paukku.md + paukku_structural.pdf
    → quality gate
```

### Renderöitävät alueet (Paukku-referenssi)

1. **Masthead** — `KUVA ERIKOIS` (musta, condensed) + `ILTA-SANOMAT` (punainen, bold italic)
2. **Meta-rivi** — numero, päivä, tähdet, hinta (ei leipätekstissä)
3. **Pääotsikot** — pää- ja alaotsikko
4. **Hero-kuva** — ainoa raster-crop
5. **Oikea sidebar** — pääjutun teksti
6. **Kuvateksti** — hero-kuvan alla
7. **Alaotsikko** — esim. LAPUA ERISTETTIIN
8. **Alapalstat** — 4–5 palstaa, min. 5.5 pt
9. **Jatkuu-laatikko** — musta tausta, valkoinen teksti

### Final text cleanup

Moduuli `src/kuvien_parsinta/text/final_text_cleanup.py` — **vain final markdown + PDF-teksti**, ei raaka-OCR:ää:

- Unicode replacement / control -merkit pois
- Pehmeät tavutusmerkit ja rivikatko-tavutukset (`on-\nnettomuus` → `onnettomuus`)
- Tunnetut literaalikorjaukset (caption, hinta, `Tapahtumahetkellä`, jne.)

### Quality gate

CLI tulostaa ajon jälkeen:

| Tulos | Merkitys |
|-------|----------|
| `QUALITY: PASS` | Sisältö, layout, typografia, cleanup ja visuaaliset metriikat OK |
| `QUALITY: PASS_WITH_WARNINGS` | Sisältö ehjä, mutta typografia/tiiviys/masthead/alapalstat vaativat vielä säätöä |
| `QUALITY: FAIL` | Sisällön puute, teksticrop, layout-kova virhe tai fontti &lt; 5.5 pt alapalstoissa |

Tarkistukset: content audit (segmentit A–H), layout-zonit PDF:stä, visual metrics, text cleanup, bottom column readability, crop policy.

Yksityiskohdat: [`docs/ERRORS.md`](docs/ERRORS.md) (ERROR-0001 … ERROR-0014).

---

## Esimerkit

### Lehtileike muotokuvalla (Koivisto)

```powershell
kuvien-parsinta parse parsittavat\Koivisto_001\koivisto2_0-1280x1280.jpg
```

→ `koivisto2_0-1280x1280.md` (teksti, `## Oikea palsta`)  
→ layout-PDF otsikko + rajattu kuva + palstat  
→ `koivisto2_0-1280x1280_photo.jpg`

### Sanomalehden etusivu (Paukku)

```powershell
kuvien-parsinta parse parsittavat\Paukku\paukku.jpg --engine hybrid --quality max
```

→ `paukku.md` — rakenteinen markdown (meta, otsikot, sidebar, kuvateksti, alapalstat)  
→ `paukku_structural.pdf` — typografioitu uudelleenrakennus  
→ `ocr/paukku_*.json` — QA-artefaktit ja quality report

### Kuulutus (flowing)

```powershell
kuvien-parsinta parse parsittavat\Kuulutus\kuulutus.jpg
```

→ yksipalstainen `.md` + yksinkertainen PDF

---

## Pikakäynnistys

```powershell
git clone https://github.com/FoxRav/doclayout-ai.git
cd doclayout-ai
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

.\scripts\activate.ps1
pip install -e ".[dev,pdf]"

# Yksittäinen tiedosto
kuvien-parsinta parse parsittavat\Paukku\paukku.jpg

# Testit (ei vaadi GPU:ta regressiossa, paitsi engine_selection)
pytest tests/ -q
```

**Syötteet:** [`parsittavat/`](parsittavat/) — luo jokaiselle työlle oma alikansio (`parsittavat/README.md`).

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
| `structurev3` | Vain PP-StructureV3 (regressio / nopea) |
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
| `auto` | **Oletus** — yksinkertainen → flowing; lehtileike/sanomalehti → layout |
| `flowing` | Yksi artikkeli / kuulutus |
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
| `PARSE_LAYOUT_PRESERVE` | `true` | Kiinnitä layout source-anchoreihin |

### Sanomalehden renderöinti

| Muuttuja | Oletus | Merkitys |
|----------|--------|----------|
| `PARSE_RENDER_TEXT_AS_IMAGE` | `false` | **Pitä olla false** — teksti ei croppeina |
| `PARSE_ALLOW_TEXT_CROPS` | `false` | Tekstialueiden raster-crop kielletty |
| `PARSE_ALLOW_PHOTO_CROPS` | `true` | Hero-kuva crop sallittu |
| `PARSE_RENDER_MASTHEAD_AS_TEXT` | `true` | Masthead PDF-tekstinä |
| `PARSE_NEWSPAPER_COMPACT` | `true` | Tiivis sanomalehtiasettelu |
| `PARSE_VERTICAL_GAP_SCALE` | `0.45` | Pystysuuntaisten välien skaala |
| `PARSE_HEADLINE_TO_IMAGE_GAP_RATIO` | `0.018` | Otsikko → hero |
| `PARSE_IMAGE_TO_CAPTION_GAP_RATIO` | `0.004` | Hero → kuvateksti |
| `PARSE_CAPTION_TO_LOWER_HEADLINE_GAP_RATIO` | `0.015` | Kuvateksti → alaotsikko |
| `PARSE_LOWER_HEADLINE_TO_COLUMNS_GAP_RATIO` | `0.010` | Alaotsikko → alapalstat |
| `PARSE_BOTTOM_COLUMN_MIN_FONT_SIZE` | `5.5` | Alapalstan min-fontti (pt) |
| `PARSE_BODY_MIN_FONT_SIZE` | `6.0` | Leipätekstin min-fontti |
| `PARSE_STRUCTURAL_MARGIN_RATIO` | `0.035` | Sivun marginaali |
| `PARSE_ALLOW_TEXT_OVERFLOW_REPORT` | `true` | Raportoi palstan ylivuodon |

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
# Oletus
kuvien-parsinta parse parsittavat\Paukku\paukku.jpg

# Vertailu
kuvien-parsinta parse parsittavat\Paukku\paukku.jpg --engine best

# Nopea regressio
kuvien-parsinta parse parsittavat\Koivisto_001\koivisto2_0-1280x1280.jpg --engine structurev3
```

---

## Reporakenne

```
├── src/kuvien_parsinta/
│   ├── cli.py, pipeline.py          # CLI & ajo
│   ├── engines/                       # VL, StructureV3, hybrid
│   ├── layout/                        # PageLayout, PageModel, source_anchors, typography
│   ├── text/                          # content_assembly, final_text_cleanup
│   ├── pdf/                           # newspaper_template_renderer, facsimile
│   └── quality/                       # content_audit, visual_metrics, quality_gate
├── tests/
│   ├── unit/                          # pytest ilman GPU:ta
│   └── regression/                    # Paukku golden-path (layout, content, cleanup)
├── scripts/                           # setup.ps1, verify_env.py, CUDA
├── docs/                              # SETUP, ROADMAP, ERRORS
├── parsittavat/                       # paikalliset syötteet (ei commitoida)
└── pyproject.toml
```

`.venv/`, `PaddleOCR/` ja `parsittavat/*` (paitsi README) eivät mene gitiin.

### Regressiotestit (sanomalehti)

| Testi | Mitä varmistaa |
|-------|----------------|
| `test_newspaper_content_completeness_paukku` | Segmentit A–H, ei forbidden-fragmentteja |
| `test_structural_pdf_text_not_cropped` | Vain photo-crop, teksti PDF:nä |
| `test_newspaper_visual_layout_metrics` | Gap-ratio, hero-leveys, font-koot |
| `test_final_text_cleanup_and_visual_warnings` | Cleanup, quality gate, alignment metrics |
| `test_newspaper_required_story_elements_rendered` | Sidebar + caption PDF:ssä |
| `test_metadata_strip_not_in_story_body` | Meta ei vuoda leipätekstiin |

---

## Tila

- [x] Hybrid pipeline (VL + StructureV3)
- [x] StructureV3 regressio (`--engine structurev3`)
- [x] Sanomalehden etusivu: PageModel, exclusive ownership, content assembly
- [x] Structural PDF: source-anchored layout, typography roles, compact spacing
- [x] Teksti aina PDF-tekstinä (ei text-croppeja); hero-kuva crop
- [x] Final text cleanup (tavutukset, kontrollimerkit, literaalit)
- [x] Quality gate: content audit + visual metrics + `PASS_WITH_WARNINGS`
- [x] Source alignment metrics, style debug, visual metrics JSON
- [x] 80 pytest-testiä
- [ ] Eräkansio / useita tiedostoja kerralla (v0.2)
- [ ] CI ilman GPU:ta

Suunnitelma: [`docs/ROADMAP.md`](docs/ROADMAP.md)
