# API du cœur Tontolo

Serveur local (127.0.0.1, jeton `Authorization: Bearer …` hors boucle locale). Schéma complet : `GET /openapi.json`. Fichier généré par `scripts/api_docs.py` : ne pas modifier à la main.

## About

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/about` | About |

## Activity

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/activity` | Tâches en cours sur cet appareil (suivi en direct depuis les autres appareils). |

## Answers

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/answers` | Réponses déjà données gardées sur l'appareil (cache sémantique). |
| `DELETE` | `/tontolo/answers` | Answers Clear |

## Browser

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/browser` | Browser Status |
| `GET` | `/tontolo/browser/next` | Tablette : prochaine commande à exécuter dans le panneau WebView (attente longue). |
| `POST` | `/tontolo/browser/result` | Browser Result |

## Catalog

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/catalog` | Catalog |
| `POST` | `/tontolo/catalog/refresh` | Refresh Catalog |

## Changes

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/changes` | Changes |
| `POST` | `/tontolo/changes/seen` | Changes Seen |

## Chat

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/tontolo/chat` | Chat |
| `POST` | `/tontolo/chat/local-media` | Enregistre dans la conversation une retouche **faite sur l'appareil** (la photo n'a |
| `POST` | `/tontolo/chat/{cid}/approve-paid` | Approve Paid |
| `POST` | `/tontolo/chat/{cid}/edit` | Edit Message |
| `POST` | `/tontolo/chat/{cid}/regenerate` | Regenerate |
| `POST` | `/tontolo/chat/{cid}/resume` | Resume |
| `POST` | `/tontolo/chat/{cid}/stop` | Stop Turn |
| `GET` | `/tontolo/chat/{cid}/stream` | Se rattacher au tour en cours (ou tout juste terminé) d'une conversation. |

## Cloud

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/cloud/creations` | Créations terminées (images, audio, fichiers…) de 1 Mo au plus, modifiées depuis |
| `POST` | `/tontolo/cloud/creations` | Création venue d'un autre appareil : fichier écrit dans le dossier des médias puis |
| `GET` | `/tontolo/cloud/export` | Conversations modifiées depuis `since` (entières) pour la synchronisation par |
| `POST` | `/tontolo/cloud/import` | Cloud Import |
| `GET` | `/tontolo/cloud/tasks` | Résultats intermédiaires modifiés depuis `since`, avec leur contenu (chiffrés par |
| `POST` | `/tontolo/cloud/tasks` | Cloud Tasks Import |

## Conversations

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/conversations` | Conversations |
| `GET` | `/tontolo/conversations/{cid}` | `tail=N` : les N derniers messages ; `before=seq&tail=N` : les N précédents (début |
| `PATCH` | `/tontolo/conversations/{cid}` | Rename |
| `DELETE` | `/tontolo/conversations/{cid}` | Delete Conv |
| `POST` | `/tontolo/conversations/{cid}/compact` | Compactage manuel : fiche structurée du début du fil (messages conservés). |
| `GET` | `/tontolo/conversations/{cid}/documents` | List Documents |
| `DELETE` | `/tontolo/conversations/{cid}/documents/{doc_id}` | Delete Document |
| `GET` | `/tontolo/conversations/{cid}/export` | Export Markdown d'une conversation (partage, archivage). |
| `PUT` | `/tontolo/conversations/{cid}/pin` | Pin |
| `DELETE` | `/tontolo/conversations/{cid}/plan` | Abandonner le plan en cours (la discussion continue normalement). |
| `GET` | `/tontolo/conversations/{cid}/tasks` | Résultats intermédiaires de la tâche (parties, étapes, sorties, brouillons). |
| `GET` | `/tontolo/conversations/{cid}/tasks/{item_id}` | Task Item |

## Custom-providers

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/custom-providers` | Custom List |
| `POST` | `/tontolo/custom-providers` | Custom Add |
| `DELETE` | `/tontolo/custom-providers/{pid}` | Custom Delete |

## Divers

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/health` | Health |

## Documents

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/tontolo/documents` | Joint une pièce (PDF, bureautique, texte, code, archive, son, vidéo…) à une |

## Feedback

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/tontolo/feedback` | 👍 / 👎 sur une réponse (0 : annuler). Renvoie le modèle et le type de demande, que |
| `PUT` | `/tontolo/feedback/global` | Notes collectives anonymes (fonction Supabase `model_scores`), relayées par l'app. |

## Folders

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/folders` | Folders |
| `PUT` | `/tontolo/folders/share` | Active ou coupe le partage de contexte entre les discussions d'un dossier. |

## Generators

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/generators` | Générateurs d'images, de vidéos et de sons, par type : prêts d'abord (gratuits |

## Health

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/health` | Model Health |

## Home

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/home` | Accueil d'une nouvelle discussion : prénom (réglage, sinon mémoire) et sujets |

## Import

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/tontolo/import` | Importe une discussion (lien de partage Claude/ChatGPT/Gemini, JSON ou texte) pour |

## Keys

| Méthode | Chemin | Rôle |
|---|---|---|
| `PUT` | `/tontolo/keys/{provider}` | Put Key |
| `DELETE` | `/tontolo/keys/{provider}` | Delete Key |

## Mcp

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/mcp` | Mcp Get |
| `PUT` | `/tontolo/mcp` | Mcp Put |

## Media

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/tontolo/media` | Media Submit |
| `GET` | `/tontolo/media` | Media List |
| `POST` | `/tontolo/media/upload` | Media Upload |
| `GET` | `/tontolo/media/{job_id}` | Media Get |
| `DELETE` | `/tontolo/media/{job_id}` | Media Delete |
| `GET` | `/tontolo/media/{job_id}/file` | Media File |

## Memory

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/memory` | Memory List |
| `POST` | `/tontolo/memory` | Memory Add |
| `DELETE` | `/tontolo/memory` | Memory Clear |
| `POST` | `/tontolo/memory/compact` | Memory Compact |
| `DELETE` | `/tontolo/memory/{mem_id}` | Memory Delete |

## Online

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/online` | Online |

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
| `GET` | `/tontolo/preferences` | Get Prefs |
| `PUT` | `/tontolo/preferences` | Put Pref |

## Providers

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/providers` | Providers |

## Route

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/tontolo/route` | « Pourquoi ce modèle ? » : décision sans appel au fournisseur. |

## Settings

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/settings` | Get Settings |
| `PUT` | `/tontolo/settings` | Put Settings |
| `GET` | `/tontolo/settings/export` | Réglages à sauvegarder ou copier sur un autre appareil : jamais de clé ni de jeton. |
| `POST` | `/tontolo/settings/import` | Settings Import |

## Spend

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/spend` | Spend |

## Status

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/status` | Status |

## Storage

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/storage` | Place occupée : données (discussions, créations, tâches…) et cache unique. |
| `POST` | `/tontolo/storage/clear-cache` | Storage Clear |

## Sync

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/sync` | Sync Export |
| `POST` | `/tontolo/sync` | Sync Import |

## Update

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/update` | Update |
| `POST` | `/tontolo/update/download` | Update Download |

## Workspace

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/tontolo/workspace` | Workspace Get |
| `PUT` | `/tontolo/workspace` | Workspace Put |
| `POST` | `/tontolo/workspace/undo` | Workspace Undo |

WebSockets : `/tontolo/ws` (événements), `/tontolo/terminal/{cid}/ws` (terminal du bureau, application locale avec jeton uniquement).
