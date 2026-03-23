# BOT Suivi Shopify

Bot local pour :

- extraire des suivis Colissimo depuis des PDF
- generer un CSV d'extraction
- marquer les commandes Shopify comme traitees avec numero de suivi

## Lancement local Windows

Le point d'entree principal est :

- `shopify_pdf_bot_platform.py`

L'application locale ecoute sur :

- `http://127.0.0.1:5000`

## Test macOS cloud

Le depot contient un smoke test macOS via GitHub Actions :

- `.github/workflows/macos-smoke-test.yml`

Documentation :

- `docs/MAC_CLOUD_TEST.md`

## Donnees locales

Les dossiers suivants ne sont pas versionnes :

- `uploads/`
- `shopify_bot_profile/`
- `.run/`
- `dist-macos/`
- `dist-windows/`
