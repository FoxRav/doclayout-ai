# doclayout-ai — lyhyt ohje

Tämä työkalu **lukee tekstin kuvista ja PDF:istä** ja tallentaa sen selkeään muotoon (markdown + structural PDF).

---

## Mitä se tekee?

1. Otat valokuvan tai skannatun sivun (jpg, png, …) — tai PDF:n
2. Työkalu tunnistaa **rakenteen ja tekstin** (PaddleOCR-VL + PP-StructureV3)
3. Saat tulokset **samaan kansioon kuin syöte**:
   - **`<nimi>.md`** — teksti muokattavassa muodossa (Markdown)
   - **`<nimi>_structural.pdf`** — uudelleenrakennettu layout-PDF (sanomalehti / lehtileike)

Ei tarvita manuaalista kirjoittamista. Teksti poimitaan kuvasta automaattisesti.

---

## Mihin sopii?

- Vanhat **kuulutukset** ja viralliset tekstit
- **Lehtileikkeet** ja artikkelit (myös kaksipalstainen asettelu)
- **Sanomalehden etusivut** (structural PDF + quality gate)
- Muut **valokuvat, joissa on luettavaa tekstiä**

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

1. Luo kansio `parsittavat/OmaTyö/` ja laita sinne kuva tai PDF
2. Avaa PowerShell **repojuuressa**
3. Aja:

```powershell
.\scripts\activate.ps1
kuvien-parsinta parse parsittavat\OmaTyö\kuva.jpg
```

4. Avaa tulokset samasta kansiosta: `kuva.md` ja `kuva_structural.pdf`

### Syötekansio

- `parsittavat/` on **paikallisia syötetiedostoja** varten — sisältöä ei commitoida.
- Repossa on vain tyhjä `parsittavat/.gitkeep`; alikansiot luot itse.

---

## Mitä tulosteessa on?

**Yksinkertainen teksti** (esim. kuulutus):
- Yksi otsikko ja yksi tai useampi kappale
- Tavut yhdistetty luettavaksi lauseeksi

**Lehtileike** (kaksi palstaa):
- Otsikko ja upotettu valokuva tunnistetaan automaattisesti
- Markdownissa **vain teksti** — palstat eroteltu
- PDF:ssä **sama rakenne kuin leikkeessä**: otsikko, rajattu kuva, teksti palstoissa

**Sanomalehti** (etusivu):
- Structural PDF typografialla (otsikot, sidebar, kuvateksti, alapalstat)
- Quality gate: `QUALITY: PASS` / `PASS_WITH_WARNINGS` / `FAIL`

**QA-artefaktit** (`ocr/`-alikansio syötteen alla):

- `ocr/<nimi>_quality_report.json`
- `ocr/<nimi>_layout_debug.jpg`
- mahdollisia OCR-JSON- ja debug-tiedostoja

Näitä **ei commitoida** — PDF:t, kuvat ja `ocr/`-tulokset ovat `.gitignore`:ssa.

Otsikko tulee **aina kuvan tekstistä**, ei tiedostonimestä.

---

## Hyödyllisiä komentoja

```powershell
# Vain markdown, ei PDF:ää
kuvien-parsinta parse parsittavat\OmaTyö\kuva.jpg --no-pdf

# Tuloste toiseen kansioon
kuvien-parsinta parse parsittavat\OmaTyö\kuva.jpg -o output\testi

# Pakota yksipalstainen tulkinta
kuvien-parsinta parse parsittavat\OmaTyö\kuva.jpg --mode flowing

# Pakota lehtileike-asettelu
kuvien-parsinta parse parsittavat\OmaTyö\kuva.jpg --mode structural
```

---

## Rajoitukset (nyt)

- Yksi tiedosto kerrallaan (ei vielä koko kansion eräajoa)
- PDF-syöte toimii; parhaiten testattu **lehtileike- ja sanomalehtikuvilla**
- OCR tekee virheitä vanhoissa tai huonoissa kuvissa; tarkista aina tulos

---

## Lisätietoa

- Tekninen README: [`README.md`](README.md)
- Asennus ja ongelmat: [`docs/SETUP.md`](docs/SETUP.md)
