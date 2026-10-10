# Todolist Tontolo v0.1.0

Légende : `[x]` fait · `[~]` en cours · `[ ]` à faire

## Phase 0 — Cadrage
- [x] Lire la spécification (`TONTOLO_PROMPT_CLAUDE_CODE.md`)
- [x] Décisions : périmètre complet, licence Apache-2.0, dépôt public, autonomie
- [x] Outillage : Flutter stable (~/development/flutter), SDK Android 36 + émulateur
- [x] Vérifier les sources en ligne (OpenRouter, AA, LMArena, mnfst, Pollinations, serious_python)

## Phase 1 — Fondations
- [ ] `core/pyproject.toml`, ruff, mypy, pytest
- [ ] `config.py` (YAML + valeurs par défaut), `secrets.py`, dossier de données
- [ ] `storage/db.py` SQLite WAL + schéma (conversations, messages, quotas, dépenses, jobs, changements)
- [ ] PoC Android : serious_python + httpx → APK, taille et démarrage mesurés, budgets fixés

## Phase 2 — Catalogue & veille
- [ ] Modèle `ModelInfo` + cache disque (TTL, ETag, mode dégradé)
- [ ] Fetchers : OpenRouter, Artificial Analysis, LMArena (datasets-server), mnfst/awesome-free-llm-apis, Pollinations
- [ ] `matcher.py` + tests sur des cas réels
- [ ] `watcher.py` : diff (new/removed/became_free…), RSS, score provisoire, fil Nouveautés
- [ ] CLI `tontolo catalog list --free --category code`

## Phase 3 — Routeur
- [ ] `classifier.py` (heuristiques FR/EN/MG + petit modèle en option)
- [ ] `scoring.py` (qualité/vitesse/fiabilité, gratuit > payant)
- [ ] Préférences manuelles (global / conversation / catégorie, mode strict)

## Phase 4 — Quotas & bascule
- [ ] `quota.py` (cooldown, épuisement journalier, Retry-After, x-ratelimit, compteurs RPM/RPD)
- [ ] Adaptation d'historique (troncature + résumé), dégradation des outils
- [ ] Moteur de bascule + retour au meilleur + événements `model_switched`
- [ ] Test d'intégration avec faux fournisseur 429

## Phase 5 — API serveur & médias
- [ ] Fournisseurs : adaptateur httpx OpenAI-compatible (+ LiteLLM optionnel sur Linux)
- [ ] FastAPI : `/v1/models`, `/v1/chat/completions` (SSE), `/v1/images/generations`, `/v1/audio/*`, WebSocket
- [ ] `MediaProvider` + jobs persistés : image (Pollinations, OpenRouter gratuits), STT (Groq), TTS (local), vidéo (meilleur effort)

## Phase 6 — Agent & MCP
- [ ] Boucle agentique, outils natifs (web_search ddgs, fetch_url, calculator, fichiers)
- [ ] Client MCP (stdio Linux, Streamable HTTP partout)
- [ ] Sécurité : confirmation des effets de bord, contenu web traité comme donnée

## Phase 7 — UI Flutter
- [ ] Maquettes (2 propositions, choix documenté)
- [ ] Chat épuré, Markdown/LaTeX/code, streaming, puce Auto ▾, bandeaux de bascule
- [ ] Créations, Nouveautés, Réglages Simple/Avancé, À propos/attributions, onboarding
- [ ] Mise en page adaptative (barre du bas / barre latérale), thème clair/sombre, i18n fr/en/mg

## Phase 8 — Deux modes + sync
- [ ] Mode local (Python embarqué) / distant (URL + jeton)
- [ ] Synchronisation de l'historique

## Phase 9 — Paiement & finitions
- [ ] Comptes payants : off/ask/auto, plafonds, journal de dépenses
- [ ] Vérification de mise à jour (API GitHub)
- [ ] Optimisations, mesures, budgets CI

## Phase 10 — Publication
- [ ] Docs : README, ARCHITECTURE, SOURCES, ATTRIBUTIONS, COMPLIANCE, RELEASING, CHANGELOG, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT
- [ ] Workflows CI + release (wheel, AppImage, APK par ABI, SHA256SUMS)
- [ ] Tests finaux (pytest, flutter test, émulateur)
- [ ] Dépôt public `raantss18/tontolo`, tag `v0.1.0`, release vérifiée
