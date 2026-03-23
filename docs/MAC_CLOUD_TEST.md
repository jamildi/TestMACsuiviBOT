# Test macOS dans le cloud

Le moyen le plus simple pour simuler un vrai environnement Mac sans posseder de Mac est d'utiliser un runner macOS heberge.

## Option recommandee

GitHub Actions avec `macos-latest`.

Pourquoi :

- vrai environnement macOS heberge par GitHub
- pratique pour verifier le premier lancement et l'auto-install
- reproductible a chaque mise a jour du bot

## Ce qui a ete prepare

Le projet contient maintenant :

- un bundle app macOS dans `dist-macos/`
- un workflow GitHub Actions dans `.github/workflows/macos-smoke-test.yml`

## Comment lancer le test

1. pousser le projet dans un depot GitHub
2. ouvrir l'onglet `Actions`
3. lancer `macOS Smoke Test`

## Ce que teste le workflow

- generation du bundle `.app`
- execution du lanceur macOS
- telechargement de micromamba
- creation de l'environnement Python
- installation des dependances
- installation de Chromium pour Playwright
- demarrage du serveur local
- verification que `http://127.0.0.1:5000/` repond bien

## Limite

Ce test valide le demarrage et le bootstrap sur un vrai runner macOS, mais pas une session Shopify manuelle avec interaction humaine. Pour cela, il faut encore un vrai Mac ou l'ordinateur de votre employe.
