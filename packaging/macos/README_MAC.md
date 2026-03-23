# BOT Suivi Shopify pour Mac

Important : cette application cible macOS uniquement.
Elle ne peut pas fonctionner sur iPhone/iPad (iOS/iPadOS), car elle lance un environnement Python local, Playwright et Chromium.

Cette version prepare un `.app` macOS auto-amorcant :

- aucune installation Python manuelle n'est necessaire sur le Mac
- au premier lancement, l'app telecharge Micromamba, cree son environnement Python, installe `flask`, `pypdf`, `playwright`, puis installe Chromium pour Playwright
- les donnees utilisateur sont stockees dans `~/Library/Application Support/BOT Suivi Shopify`
- l'interface s'ouvre ensuite sur `http://127.0.0.1:5000`

## Contenu du package

Le bundle genere contient :

- l'application `BOT Suivi Shopify.app`
- le code Python du bot embarque dans `Contents/Resources/payload`

## Premiere ouverture sur Mac

Comme le bundle est prepare hors macOS et n'est pas signe, macOS peut demander :

1. clic droit sur l'application
2. `Ouvrir`
3. confirmer l'ouverture

Si le Mac perd le bit executable pendant le transfert, lancer une fois :

```bash
chmod +x "BOT Suivi Shopify.app/Contents/MacOS/bot-suivi-shopify"
```

## Mise a jour du bot

Relancer le script de build Windows pour regenerer `dist-macos/BOT Suivi Shopify.app` avec la derniere version du code.
