# doclayout-ai — lyhyt ohje

Tämä työkalu **lukee tekstin kuvista ja PDF:istä** ja tuottaa rakenteisen markdownin sekä structural PDF:n.

---

## Mitä se tekee?

1. Otat valokuvan tai skannatun sivun (jpg, png, …) — tai PDF:n
2. Työkalu tunnistaa **rakenteen ja tekstin** (PaddleOCR-VL + PP-StructureV3)
3. Saat tulokset **samaan kansioon kuin syöte**:
   - **`<nimi>.md`** — rakenteinen teksti (Markdown)
   - **`<nimi>_structural.pdf`** — uudelleenrakennettu layout-PDF

---

## Mihin sopii?

- Skannatut asiakirjat ja sivut, joissa on luettavaa tekstiä
- Monipalstaiset layoutit ja dokumentit, joissa on otsikoita, kuvia ja tekstilohkoja
- PDF-syöte (yksi tai useampi sivu)

Ensisijainen kieli on **suomi**, mutta työkalu tunnistaa myös ruotsia, englantia ja muita kieliä.

---

## Miten käytän?

### Ensimmäinen kerta (asennus, kerran)

```powershell
git clone https://github.com/FoxRav/doclayout-ai.git
cd doclayout-ai
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Asennus kestää noin 15–30 minuuttia. Tarvitset Python 3.10:n ja NVIDIA-näytönohjaimen (suositeltu).

### Joka kerta

1. Luo kansio `parsittavat/example/` ja lisää sinne kuva tai PDF
2. Avaa PowerShell **repojuuressa**
3. Aja:

```powershell
.\scripts\activate.ps1
kuvien-parsinta parse parsittavat\example\document.jpg --engine hybrid --quality max
```

4. Avaa tulokset samasta kansiosta: `document.md`, `document_structural.pdf`, `ocr/document_quality_report.json`

### Syötekansio

- `parsittavat/` on **paikallisia syötetiedostoja** varten — sisältöä ei commitoida
- Repossa on vain `parsittavat/.gitkeep`; alikansiot luot itse

---

## Mitä tulosteessa on?

- **Markdown** — otsikot, kappaleet ja dokumentin rakenne PageModelista
- **Structural PDF** — uudelleenrakennettu sivu (ei koko skannauksen taustakuvaa)
- **Quality report** — `ocr/<nimi>_quality_report.json` (PASS / PASS_WITH_WARNINGS / FAIL)
- **Debug** — layout-kuva, OCR-JSON, typografia- ja visual-metriikat `ocr/`-kansiossa

Näitä **ei commitoida** — generoidut PDF:t, kuvat ja `ocr/`-tulokset ovat `.gitignore`:ssa.

---

## Hyödyllisiä komentoja

```powershell
# Vain markdown, ei PDF:ää
kuvien-parsinta parse parsittavat\example\document.jpg --no-pdf

# Tuloste toiseen kansioon
kuvien-parsinta parse parsittavat\example\document.jpg -o output\run1

# Pakota yksipalstainen tulkinta
kuvien-parsinta parse parsittavat\example\document.jpg --mode flowing

# Pakota structural layout
kuvien-parsinta parse parsittavat\example\document.jpg --mode structural
```

---

## Rajoitukset (nyt)

- Yksi tiedosto kerrallaan (ei vielä koko kansion eräajoa)
- OCR tekee virheitä vanhoissa tai huonoissa kuvissa; tarkista aina tulos

---

## Lisätietoa

- Tekninen README: [`README.md`](README.md)
- Asennus ja ongelmat: [`docs/SETUP.md`](docs/SETUP.md)
