# Asennus (itsenäinen ympäristö)

Kaikki asennukset tapahtuvat **vain** repokansion `.venv`-hakemistoon.
Järjestelmän Pythonia, PATH:ia tai globaalia pip:ä **ei muuteta**.

## Projektin hankinta

```powershell
git clone https://github.com/FoxRav/doclayout-ai.git
cd doclayout-ai
```

Repojuuren rakenne:

```
doclayout-ai/
├── .venv/              ← ainoa Python-ympäristö (ei gitiin)
├── PaddleOCR/          ← upstream-klooni (git clone setup.ps1:llä)
├── parsittavat/        ← paikalliset syötteet (vain .gitkeep repossa)
├── requirements/       ← OCR-extras (setup.ps1)
├── scripts/            ← setup, verify_env, CUDA
├── src/kuvien_parsinta/← sovelluskoodi
├── tests/              ← unit- ja regressiotestit
└── .env                ← paikallinen konfig (ei commitoida)
```

## Vaatimukset

- Windows 10/11
- **Python 3.10.x** (asennettu, esim. `py -3.10`)
- **Git** (PaddleOCR-klooni)
- **NVIDIA GPU + ajuri** (OCR GPU:lla; CPU fallback mahdollinen mutta hidas)
- Docker **ei** pakollinen

## Yksi komento

Aja repojuuresta:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Skripti:

1. Luo `.venv` (Python 3.10)
2. Kloonaa `PaddleOCR/` (shallow)
3. Asentaa `paddlepaddle-gpu` (CUDA 11.8)
4. Asentaa `paddleocr[all]` editable-tilassa
5. Asentaa OCR-extras + **torch 2.5.1+cu118** (CUDA, sama kuin Paddle)
6. Asentaa `kuvien-parsinta` + fpdf2 + dev-työkalut
7. Asentaa torch/Paddle **DLL-preload hookin** venv:iin (Windows)
8. Luo `.env` pohjalta `.env.example`:sta
9. Ajaa `scripts/verify_env.py` + pytest

**CUDA-päivitys olemassa olevaan venv:iin** (ilman täyttä setupia):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_cuda.ps1
```

Kesto: noin 15–30 min (verkosta riippuen).

## Päivittäinen käyttö

```powershell
.\scripts\activate.ps1          # tai .\.venv\Scripts\Activate.ps1
kuvien-parsinta parse parsittavat\example.jpg
```

**Älä** aja `pip install` ilman aktivoitua `.venv`:ä.

## Syötekansio (`parsittavat/`)

- Tarkoitettu **paikallisille** kuville ja PDF:ille — ei commitoida repoon.
- `parsittavat/*` on `.gitignore`:ssa; repossa on vain `parsittavat/.gitkeep`.
- Luo itse alikansiot (esim. `parsittavat/OmaTyö/`) ja lisää syötteet sinne.
- Tulosteet syntyvät **samaan kansioon** kuin syöte (esim. `parsittavat/OmaTyö/kuva.md`).

## Tulosteet (ei gitiin)

Normaali ajo tuottaa syötekansion viereen:

| Tiedosto | Sisältö |
|----------|---------|
| `<nimi>.md` | Päämarkdown |
| `<nimi>_structural.pdf` | Uudelleenrakennettu layout-PDF |
| `ocr/<nimi>_quality_report.json` | Quality gate -raportti |
| `ocr/<nimi>_layout_debug.jpg` | Layout-debug-kuva |

Lisäksi `ocr/`-kansioon voi syntyä OCR-JSON, style debug, visual metrics jne.

**Näitä ei commitoida:** `.gitignore` sulkee pois `ocr/`, `*.pdf`, `*.jpg`, `*.png` ja muut generoidut artefaktit.

## Tarkista ympäristö

```powershell
.\.venv\Scripts\python.exe scripts\verify_env.py
```

Odotettu: `All checks passed.` + `paddle.utils.run_check()` OK.

## Torch + Paddle DLL (Windows)

Repo sisältää Windows-kohtaisen DLL-preload -koukun:

- `scripts/_paddleocr_preload.py`
- `scripts/_paddleocr_torch_dll_fix.pth`

`setup.ps1` kopioi ne → `.venv/Lib/site-packages/`. Ilman koukkua
`import albumentations` Paddle-importin jälkeen voi kaatua (`shm.dll`).

## CUDA-käyttö

| Komponentti | Laite | Konfig |
|-------------|-------|--------|
| Paddle OCR / Structure | GPU kun saatavilla | `PARSE_OCR_DEVICE=auto` (oletus) |
| PyTorch (VL-fallback) | CUDA kun saatavilla | automaattinen |
| ONNX Runtime | CUDAExecutionProvider ensin | automaattinen |

`auto` valitsee `gpu:0` jos Paddle näkee CUDA-laitteen, muuten `cpu`.
Pakota CPU: `PARSE_OCR_DEVICE=cpu`.

## Ongelmat

| Ongelma | Ratkaisu |
|---------|----------|
| `Python 3.10 required` | Asenna 3.10.x, käytä `py -3.10` |
| `paddle.utils.run_check` GPU fail | Päivitä NVIDIA-ajuri; sulje muut GPU-prosessit |
| `ImportError: paddleocr` | Aja `setup.ps1` uudelleen |
| Väärä Python | Varmista `where python` → polussa `.venv\Scripts` |

## Uudelleenasennus

```powershell
Remove-Item -Recurse -Force .venv, PaddleOCR -ErrorAction SilentlyContinue
powershell -File scripts\setup.ps1
```

Tämä **ei** poista `parsittavat/`-syötteitä eikä niiden rinnalle syntyneitä tulosteita.
