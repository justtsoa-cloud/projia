# API du cœur Projia

Serveur local (127.0.0.1, jeton `Authorization: Bearer …` hors boucle locale). Schéma complet : `GET /openapi.json`. Fichier généré par `scripts/api_docs.py` : ne pas modifier à la main.

## About

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/about` | About |

## Activity

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/activity` | Tâches en cours sur cet appareil (suivi en direct depuis les autres appareils). |

## Answers

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/answers` | Réponses déjà données gardées sur l'appareil (cache sémantique). |
| `DELETE` | `/projia/answers` | Answers Clear |

## Browser

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/browser` | Browser Status |
| `GET` | `/projia/browser/next` | Tablette : prochaine commande à exécuter dans le panneau WebView (attente longue). |
| `POST` | `/projia/browser/result` | Browser Result |

## Catalog

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/catalog` | Catalog |
| `POST` | `/projia/catalog/refresh` | Refresh Catalog |

## Changes

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/changes` | Changes |
| `POST` | `/projia/changes/seen` | Changes Seen |

## Chat

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/projia/chat` | Chat |
| `POST` | `/projia/chat/local-media` | Enregistre dans la conversation une retouche **faite sur l'appareil** (la photo n'a |
| `POST` | `/projia/chat/{cid}/approve-paid` | Approve Paid |
| `POST` | `/projia/chat/{cid}/edit` | Edit Message |
| `POST` | `/projia/chat/{cid}/regenerate` | Regenerate |
| `POST` | `/projia/chat/{cid}/resume` | Resume |
| `POST` | `/projia/chat/{cid}/stop` | Stop Turn |
| `GET` | `/projia/chat/{cid}/stream` | Se rattacher au tour en cours (ou tout juste terminé) d'une conversation. |

## Cloud

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/cloud/creations` | Créations terminées (images, audio, fichiers…) de 1 Mo au plus, modifiées depuis |
| `POST` | `/projia/cloud/creations` | Création venue d'un autre appareil : fichier écrit dans le dossier des médias puis |
| `GET` | `/projia/cloud/export` | Conversations modifiées depuis `since` (entières) pour la synchronisation par |
| `POST` | `/projia/cloud/import` | Cloud Import |
| `GET` | `/projia/cloud/tasks` | Résultats intermédiaires modifiés depuis `since`, avec leur contenu (chiffrés par |
| `POST` | `/projia/cloud/tasks` | Cloud Tasks Import |

## Conversations

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/conversations` | Conversations |
| `GET` | `/projia/conversations/{cid}` | `tail=N` : les N derniers messages ; `before=seq&tail=N` : les N précédents (début |
| `PATCH` | `/projia/conversations/{cid}` | Rename |
| `DELETE` | `/projia/conversations/{cid}` | Delete Conv |
| `POST` | `/projia/conversations/{cid}/compact` | Compactage manuel : fiche structurée du début du fil (messages conservés). |
| `GET` | `/projia/conversations/{cid}/documents` | List Documents |
| `DELETE` | `/projia/conversations/{cid}/documents/{doc_id}` | Delete Document |
| `GET` | `/projia/conversations/{cid}/export` | Export Markdown (par défaut) ou PDF d'une conversation (partage, archivage) ; |
| `PUT` | `/projia/conversations/{cid}/pin` | Pin |
| `DELETE` | `/projia/conversations/{cid}/plan` | Abandonner le plan en cours (la discussion continue normalement). |
| `GET` | `/projia/conversations/{cid}/tasks` | Résultats intermédiaires de la tâche (parties, étapes, sorties, brouillons). |
| `GET` | `/projia/conversations/{cid}/tasks/{item_id}` | Task Item |

## Custom-providers

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/custom-providers` | Custom List |
| `POST` | `/projia/custom-providers` | Custom Add |
| `DELETE` | `/projia/custom-providers/{pid}` | Custom Delete |

## Divers

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/health` | Health |

## Documents

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/projia/documents` | Joint une pièce (PDF, bureautique, texte, code, archive, son, vidéo…) à une |

## Execution

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/execution/capabilities` | Execution Capabilities |

## Explainer

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/explainer/capabilities` | Ce que cette machine sait faire : le lecteur animé de l'application marche partout ; |
| `POST` | `/projia/explainer/render` | MP4 d'un scénario (corps : {"story": {...}, "quality": "l"|"m"}). Le scénario est |

## Feedback

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/projia/feedback` | 👍 / 👎 sur une réponse (0 : annuler). Renvoie le modèle et le type de demande, que |
| `PUT` | `/projia/feedback/global` | Notes collectives anonymes (fonction Supabase `model_scores`), relayées par l'app. |

## Folders

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/folders` | Folders |
| `PUT` | `/projia/folders/share` | Active ou coupe le partage de contexte entre les discussions d'un dossier. |

## Generators

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/generators` | Générateurs d'images, de vidéos et de sons, par type : prêts d'abord (gratuits |

## Health

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/health` | Model Health |

## Home

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/home` | Accueil d'une nouvelle discussion : prénom (réglage, sinon mémoire) et sujets |
| `POST` | `/projia/home/dismiss` | « Pas pour moi » : ce thème n'est plus proposé pendant deux semaines. |

## Import

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/projia/import` | Importe une discussion (lien de partage Claude/ChatGPT/Gemini, JSON ou texte) pour |

## Keys

| Méthode | Chemin | Rôle |
|---|---|---|
| `PUT` | `/projia/keys/{provider}` | Put Key |
| `DELETE` | `/projia/keys/{provider}` | Delete Key |

## Mcp

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/mcp` | Mcp Get |
| `PUT` | `/projia/mcp` | Mcp Put |

## Media

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/projia/media` | Media Submit |
| `GET` | `/projia/media` | Media List |
| `POST` | `/projia/media/upload` | Media Upload |
| `GET` | `/projia/media/{job_id}` | Media Get |
| `DELETE` | `/projia/media/{job_id}` | Media Delete |
| `GET` | `/projia/media/{job_id}/file` | Media File |

## Memory

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/memory` | Memory List |
| `POST` | `/projia/memory` | Memory Add |
| `DELETE` | `/projia/memory` | Memory Clear |
| `POST` | `/projia/memory/compact` | Memory Compact |
| `DELETE` | `/projia/memory/{mem_id}` | Memory Delete |

## Metrics

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/metrics` | Métriques locales au format Prometheus (rien n'est envoyé ailleurs). |

## Online

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/online` | Online |

## OpenAI (compatible)

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/v1/audio/speech` | V1 Speech |
| `POST` | `/v1/audio/transcriptions` | V1 Transcribe |
| `POST` | `/v1/chat/completions` | V1 Chat |
| `POST` | `/v1/images/generations` | V1 Images |
| `GET` | `/v1/models` | V1 Models |

## Preferences

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/preferences` | Get Prefs |
| `PUT` | `/projia/preferences` | Put Pref |

## Providers

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/providers` | Providers |

## Route

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/projia/route` | « Pourquoi ce modèle ? » : décision sans appel au fournisseur. |

## Settings

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/settings` | Get Settings |
| `PUT` | `/projia/settings` | Put Settings |
| `GET` | `/projia/settings/export` | Réglages à sauvegarder ou copier sur un autre appareil : jamais de clé ni de jeton. |
| `POST` | `/projia/settings/import` | Settings Import |

## Spend

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/spend` | Spend |

## Status

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/status` | Status |

## Storage

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/storage` | Place occupée : données (discussions, créations, tâches…) et cache unique. |
| `POST` | `/projia/storage/clear-cache` | Storage Clear |

## Sync

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/sync` | Sync Export |
| `POST` | `/projia/sync` | Sync Import |

## Update

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/update` | Update |
| `POST` | `/projia/update/download` | Update Download |

## Workspace

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/projia/workspace` | Workspace Get |
| `PUT` | `/projia/workspace` | Workspace Put |
| `POST` | `/projia/workspace/undo` | Workspace Undo |

WebSockets : `/projia/ws` (événements), `/projia/terminal/{cid}/ws` (terminal du bureau, application locale avec jeton uniquement).
