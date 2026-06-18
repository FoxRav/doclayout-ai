# Parsittavat tiedostot

Laita jokaisen työn kuvat ja PDF:t **omaan alikansioon** tähän hakemistoon.

```
parsittavat/
├── Seppo_Niemi/
│   ├── Puolanka_0002.png
│   └── ...
├── Martti1/
│   └── ...
└── <uusi_työ>/          ← luo uusi kansio joka kerta
    └── ...
```

Tulokset syntyvät **samaan kansioon kuin syöte**: `<nimi>.md`, `<nimi>.pdf`, valinnaisesti `<nimi>_photo.jpg` ja `ocr/`-alikansio.

## Ajo

```powershell
cd F:\-DEV-\95.Kuvien-parsinta-SOTA
.\scripts\activate.ps1

# yksi tiedosto
kuvien-parsinta parse parsittavat\Seppo_Niemi\Puolanka_0002.png

# useita tiedostoja samasta työstä (PowerShell)
Get-ChildItem parsittavat\Seppo_Niemi\*.{png,jpg,pdf} | ForEach-Object {
    kuvien-parsinta parse $_.FullName
}
```

Tämä kansio ei mene gitiin (paitsi tämä README).
