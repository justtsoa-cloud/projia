# Architecture de Tontolo

```
┌──────────────── Application Flutter (Android · Linux) ────────────────┐
│  Chat · Créations · Réglages · Nouveautés · mises à jour automatiques │
│                       HTTP + SSE (même code)                          │
└───────────────┬───────────────────────────────────┬───────────────────┘
        mode local (127.0.0.1 + jeton aléatoire)    mode distant (URL + jeton)
                │                                   │
┌───────────────▼───────── Cœur Python `tontolo` ───▼──────────────────┐
│ server/  FastAPI : /v1 (compatible OpenAI) · /tontolo (natif) · WS   │
│ agent/   boucle agentique · outils natifs · MCP (SDK ou client léger)│
│ router/  classifier → scoring → engine (bascule, retour) · quota     │
│ media/   jobs persistés : image · STT · TTS · musique · vidéo        │
│ catalog/ sources en ligne → matcher → catalogue classé · veille      │
│ providers/ adaptateur httpx compatible OpenAI (LiteLLM en option)    │
│ storage/ SQLite WAL : historique canonique, quotas, dépenses, jobs   │
└──────────────────────────────────────────────────────────────────────┘
```

## Flux d'une demande

1. **Classification** (`router/classifier.py`) : heuristiques FR/EN/MG → `TaskProfile`
   (catégorie, modalité, outils, vision, contexte minimal). Petit modèle gratuit en option
   si la demande est ambiguë.
2. **Classement** (`router/scoring.py`) : modèles éligibles (capacités, contexte, fournisseur
   utilisable, hors attente), `score = w_q·Q + w_s·V + w_r·F − pénalités`, gratuit avant
   payant, modèle préféré en tête. Sélection mesurée < 1 ms (budget 20 ms).
3. **Exécution** (`router/engine.py`) : appel du premier candidat ; sur erreur → état de quota
   mis à jour, événement `model_switched`, candidat suivant. Historique adapté au contexte du
   nouveau modèle (résumé conservé en base). En flux : `stream_reset` puis relance propre.
4. **Retour** : au tour suivant, le classement est recalculé ; un modèle sorti d'attente
   reprend sa place (`model_returned`). Aucune requête de test n'est jamais envoyée.

## Catalogue et veille

Sources (aucune donnée codée en dur) : OpenRouter (catalogue + indices AA intégrés),
Pollinations (sans clé), mnfst/awesome-free-llm-apis (fournisseurs gratuits), Artificial
Analysis (clé gratuite), LMArena (CC BY 4.0). Cache disque avec TTL et ETag ; démarrage
instantané depuis le cache, rafraîchissement en arrière-plan à l'ouverture et à chaque
nouvelle conversation. `catalog/matcher.py` apparie les noms entre sources (version, gamme
et taille doivent concorder). `catalog/watcher.py` produit le fil « Nouveautés ».

## Choix techniques et écarts assumés vis-à-vis de la spécification

| Sujet | Choix | Raison |
|---|---|---|
| Licence | **Apache-2.0** (au lieu de MIT) | Décision du mainteneur : permissive + licence de brevets ; compatible avec toutes les dépendances. |
| LiteLLM | Optionnel (Linux, `TONTOLO_USE_LITELLM=1`) ; adaptateur httpx par défaut partout | LiteLLM tire tiktoken/tokenizers/aiohttp : trop lourd pour l'APK. Un seul chemin de code testé. |
| Recherche web sous Android | Repli HTML DuckDuckGo en httpx | `ddgs` ajoute primp + lxml (≈ 16 Mo par ABI). |
| MCP sous Android | Client Streamable HTTP léger (`agent/mcp_lite.py`) | Le SDK tire cryptography, jsonschema, opentelemetry (≈ 14 Mo par ABI). |
| Découverte des fournisseurs | mnfst/awesome-free-llm-apis | cheahjs/free-llm-api-resources introuvable (404). |
| Médias OpenRouter | Gratuits seulement si `:free` | Prix texte nul affiché pour des modèles facturés à l'unité. |
| Mises à jour | Automatiques (demande du mainteneur) | Linux : remplacement de l'AppImage vérifiée (SHA-256) ; Android : installeur système en un appui (pas d'installation silencieuse possible). |
| Paiement | Plafond > 0 obligatoire | Aucun appel payant sans plafond explicite. |

## Mémoire

`tontolo/memory.py` : souvenirs locaux (table `memories`). Capture explicite
(« souviens-toi que… ») et extraction automatique tous les 4 messages par un petit modèle
gratuit ; rappel par pertinence dans un budget de caractères ; compactage automatique au-delà
de `memory_max_items` (fusion locale des doublons, puis regroupement par modèle, sinon retrait
des moins utiles). Les secrets sont filtrés avant tout enregistrement. L'historique de chaque
conversation est en plus résumé automatiquement quand il dépasse le contexte du modèle.

## Sécurité

- Cœur embarqué : écoute sur 127.0.0.1 uniquement, jeton aléatoire de 256 bits par lancement.
- Serveur distant : jeton obligatoire hors boucle locale (refus de démarrer sinon).
- Clés : Keystore Android / libsecret (application), trousseau ou fichier 0600 (CLI) ;
  jamais en base ni dans les journaux.
- Contenu web et MCP encadré comme donnée non fiable ; outils à effet de bord soumis à
  confirmation ; calculatrice limitée à un sous-ensemble mathématique validé, avec délai.
- Serveur local : refus des en-têtes `Origin` étrangers (CSRF) et des `Host` non locaux
  (DNS rebinding) ; WebSocket idem.
- `fetch_url` : pas d'adresse privée, locale ou de métadonnées cloud, redirections
  revérifiées, 2 Mo maximum (`security.py`, `tools.safe_get`).
- Fournisseurs : clé envoyée seulement en HTTPS à l'hôte épinglé à la première utilisation
  (`provider_pins.json`) ; un changement d'hôte dans la source en ligne est refusé.
- Serveurs MCP `stdio` : configuration locale uniquement. Envois limités à 25 Mo.
- Application : liens limités à http(s)/mailto, mises à jour uniquement depuis GitHub avec
  SHA-256, signature APK vérifiée par Android, `allowBackup=false`.


## Frontières de contexte (0.5.0)

Les dossiers organisent les discussions sans partager leur contexte. Les souvenirs explicites
et manuels sont rappelables entre fils ; les extractions automatiques conservent leur origine
et ne sont pas injectées dans un autre fil. Le compactage conserve la provenance et sérialise
les mutations. Voir [Isolation du contexte](CONTEXT_ISOLATION.md) pour les références médias,
les tests et le traitement des anciens souvenirs compactés sans origine.
