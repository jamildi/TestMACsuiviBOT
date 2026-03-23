# BOT Suivi Shopify pour Windows

Cette version prepare un lanceur Windows autonome :

- double-clic sur `BOT Suivi Shopify.cmd`
- au premier lancement, telechargement de Python embarque
- installation automatique de `pip`, `flask`, `pypdf`, `playwright`
- installation automatique de Chromium pour Playwright
- ouverture de l'interface sur `http://127.0.0.1:5000`

Les donnees utilisateur sont stockees dans :

- `%LOCALAPPDATA%\\BOT Suivi Shopify`

Le dossier peut etre transfere vers un autre PC Windows.

Si SmartScreen avertit au premier lancement, choisir :

- `Informations complementaires`
- `Executer quand meme`
