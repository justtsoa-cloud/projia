# Todolist Tontolo v0.1.0

Légende : `[x]` fait · `[~]` en cours · `[ ]` à faire

## Phase 0 — Cadrage
- [x] Lire la spécification (`TONTOLO_PROMPT_CLAUDE_CODE.md`)
- [x] Décisions : périmètre complet, licence Apache-2.0, dépôt public, autonomie
- [x] Outillage : Flutter stable (~/development/flutter), SDK Android 36 + émulateur
- [x] Vérifier les sources en ligne (OpenRouter, AA, LMArena, mnfst, Pollinations, serious_python)

## Phase 1 — Fondations
- [x] `core/pyproject.toml`, ruff, mypy, pytest
- [x] `config.py` (YAML + valeurs par défaut), `secrets.py`, dossier de données
- [x] `storage/db.py` SQLite WAL + schéma (conversations, messages, quotas, dépenses, jobs, changements)
- [x] PoC Android : serious_python + httpx → APK, taille et démarrage mesurés, budgets fixés

## Phase 2 — Catalogue & veille
- [x] Modèle `ModelInfo` + cache disque (TTL, ETag, mode dégradé)
- [x] Fetchers : OpenRouter, Artificial Analysis, LMArena (datasets-server), mnfst/awesome-free-llm-apis, Pollinations
- [x] `matcher.py` + tests sur des cas réels
- [x] `watcher.py` : diff (new/removed/became_free…), RSS, score provisoire, fil Nouveautés
- [x] CLI `tontolo catalog list --free --category code`

## Phase 3 — Routeur
- [x] `classifier.py` (heuristiques FR/EN/MG + petit modèle en option)
- [x] `scoring.py` (qualité/vitesse/fiabilité, gratuit > payant)
- [x] Préférences manuelles (global / conversation / catégorie, mode strict)

## Phase 4 — Quotas & bascule
- [x] `quota.py` (cooldown, épuisement journalier, Retry-After, x-ratelimit, compteurs RPM/RPD)
- [x] Adaptation d'historique (troncature + résumé), dégradation des outils
- [x] Moteur de bascule + retour au meilleur + événements `model_switched`
- [x] Test d'intégration avec faux fournisseur 429

## Phase 5 — API serveur & médias
- [x] Fournisseurs : adaptateur httpx OpenAI-compatible (+ LiteLLM optionnel sur Linux)
- [x] FastAPI : `/v1/models`, `/v1/chat/completions` (SSE), `/v1/images/generations`, `/v1/audio/*`, WebSocket
- [x] `MediaProvider` + jobs persistés : image (Pollinations, OpenRouter gratuits), STT (Groq), TTS (local), vidéo (meilleur effort)

## Phase 6 — Agent & MCP
- [x] Boucle agentique, outils natifs (web_search ddgs, fetch_url, calculator, fichiers)
- [x] Client MCP (stdio Linux, Streamable HTTP partout)
- [x] Sécurité : confirmation des effets de bord, contenu web traité comme donnée

## Phase 7 — UI Flutter
- [x] Maquettes (2 propositions, choix documenté)
- [x] Chat épuré, Markdown/LaTeX/code, streaming, puce Auto ▾, bandeaux de bascule
- [x] Créations, Nouveautés, Réglages Simple/Avancé, À propos/attributions, onboarding
- [x] Mise en page adaptative (barre du bas / barre latérale), thème clair/sombre, i18n fr/en/mg

## Phase 8 — Deux modes + sync
- [x] Mode local (Python embarqué) / distant (URL + jeton)
- [x] Synchronisation de l'historique

## Phase 9 — Paiement & finitions
- [x] Comptes payants : off/ask/auto, plafonds, journal de dépenses
- [x] Mises à jour automatiques depuis les releases GitHub (demande du 2026-10-10) :
      Linux = téléchargement + SHA-256 + remplacement de l'AppImage + redémarrage ;
      Android = téléchargement de l'APK (ABI) + SHA-256 + installeur système (1 appui)
- [x] Optimisations, mesures, budgets CI

## Phase 10 — Publication
- [x] Docs : README, ARCHITECTURE, SOURCES, ATTRIBUTIONS, COMPLIANCE, RELEASING, CHANGELOG, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT
- [x] Workflows CI + release (wheel, AppImage, APK par ABI, SHA256SUMS)
- [x] Tests finaux (pytest, flutter test, émulateur)
- [ ] Dépôt public `raantss18/tontolo`, tag `v0.1.0`, release vérifiée
