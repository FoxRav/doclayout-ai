# Kuvien-parsinta-SOTA — lyhyt ohje

Tämä työkalu **lukee tekstin kuvista** (ja myöhemmin PDF:istä) ja tallentaa sen selkeään muotoon.

---

## Mitä se tekee?

1. Otat valokuvan tai skannatun sivun (jpg, png, …) — tai PDF:n
2. Työkalu tunnistaa **rakenteen ja tekstin** (PP-StructureV3 + OCR)
3. Saat kaksi tiedostoa **samaan kansioon kuin kuva**:
   - **`.md`** — teksti muokattavassa muodossa (Markdown)
   - **`.pdf`** — valmis lukukappale

Ei tarvita manuaalista kirjoittamista. Teksti poimitaan kuvasta automaattisesti.

---

## Mihin sopii?

- Vanhat **kuulutukset** ja viralliset tekstit
- **Lehtileikkeet** ja artikkelit (myös kaksipalstainen asettelu)
- Muut **valokuvat, joissa on luettavaa tekstiä**

Ensisijainen kieli on **suomi**, mutta työkalu tunnistaa myös ruotsia, englantia ja muita kieliä.

---

## Miten käytän?

### Ensimmäinen kerta (asennus, kerran)

```powershell
cd F:\-DEV-\95.Kuvien-parsinta-SOTA
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Asennus kestää noin 15–30 minuuttia. Tarvitset Python 3.10:n ja NVIDIA-näytönohjaimen (suositeltu).

### Joka kerta

1. Laita kuva kansioon `parsittavat/` (esim. `parsittavat/OmaTyö/kuva.jpg`)
2. Avaa PowerShell repokansiossa
3. Aja:

```powershell
.\scripts\activate.ps1
kuvien-parsinta parse parsittavat\OmaTyö\kuva.jpg
```

4. Avaa tulokset samasta kansiosta: `kuva.md` ja `kuva.pdf`

---

## Mitä tulosteessa on?

**Yksinkertainen teksti** (esim. kuulutus):
- Yksi otsikko ja yksi tai useampi kappale
- Tavut yhdistetty luettavaksi lauseeksi

**Lehtileike** (kaksi palstaa, esim. Koivisto):
- Otsikko ja upotettu valokuva tunnistetaan automaattisesti (PP-StructureV3)
- Markdownissa **vain teksti** — palstat eroteltu (`## Oikea palsta` jne.)
- PDF:ssä **sama rakenne kuin leikkeessä**: otsikko, rajattu kuva vasemmalla, teksti oikealla (yksi sivu)
- Erillinen `<nimi>_photo.jpg` — pelkkä tunnistettu muotokuva

Otsikko tulee **aina kuvan tekstistä**, ei tiedostonimestä.

---

## Hyödyllisiä komentoja

```powershell
# Vain markdown, ei PDF:ää
kuvien-parsinta parse kuva.jpg --no-pdf

# Tuloste toiseen kansioon
kuvien-parsinta parse kuva.jpg -o output\testi

# Pakota yksipalstainen tulkinta
kuvien-parsinta parse kuva.jpg --mode flowing

# Pakota lehtileike-asettelu
kuvien-parsinta parse kuva.jpg --mode structural
```

---

## Rajoitukset (nyt)

- Yksi tiedosto kerrallaan (ei vielä koko kansion eräajoa)
- PDF-syöte toimii (yksisivuiset ja monisivuiset); parhaiten testattu **lehtileike-kuvilla**
- OCR tekee virheitä vanhoissa tai huonoissa kuvissa; tarkista aina tulos

---

## Lisätietoa

- Tekninen README: [`README.md`](README.md)
- Asennus ja ongelmat: [`docs/SETUP.md`](docs/SETUP.md)
