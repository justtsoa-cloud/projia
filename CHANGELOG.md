# Journal des modifications

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement
[SemVer](https://semver.org/lang/fr/).

## [Non publié]

## [0.1.0] - 2026-10-10

### Ajouté
- Cœur Python `tontolo` : catalogue en ligne (OpenRouter, Artificial Analysis, LMArena,
  awesome-free-llm-apis, Pollinations), cache TTL/ETag, appariement des modèles, veille.
- Routage automatique vers le meilleur modèle gratuit par catégorie de tâche (FR/EN/MG),
  choix manuel (global, conversation, catégorie, mode strict).
- Quotas, bascule sans perte d'historique, adaptation au contexte, retour au meilleur modèle.
- Serveur compatible OpenAI (`/v1/chat/completions`, `/v1/models`, `/v1/images/generations`,
  `/v1/audio/transcriptions`, `/v1/audio/speech`), API native et WebSocket.
- Médias : images (Pollinations sans clé…), transcription, synthèse vocale (repli local),
  vidéo au mieux ; jobs persistés.
- Agent : recherche web sourcée, lecture d'URL, calculatrice, fichiers, client MCP.
- Comptes payants optionnels avec plafonds et journal de dépenses.
- Application Flutter Android et Linux : chat épuré, Markdown/LaTeX, sélecteur « Auto »,
  Créations, Nouveautés, réglages Simple/Avancé, mode local/distant, synchronisation,
  mises à jour automatiques vérifiées (SHA-256).
- CLI `tontolo` (catalog, route, chat, keys, serve).
