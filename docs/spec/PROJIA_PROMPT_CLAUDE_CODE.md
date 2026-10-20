# Prompt Claude Code — Projet « Projia »

> Copiez tout ce qui suit dans Claude Code, à la racine d'un dépôt vide nommé `projia`.

---

## 0. Rôle et méthode

Tu es l'architecte et le développeur principal de **Projia**, un client/routeur d'IA libre et gratuit (licence MIT) pour **Linux et Android**.

Règles de travail :
1. **Vérifie avant de coder.** Les quotas gratuits et les API changent souvent : avant chaque intégration, consulte la documentation officielle à jour (OpenRouter, Artificial Analysis, LMArena, LiteLLM, MCP, serious_python, ddgs) et note la date de vérification dans `docs/SOURCES.md`.
2. **Ne code jamais en dur** une liste de modèles, un classement ou un quota. Tout vient des plateformes en ligne (section 3).
3. Travaille par **phases** (section 8). À la fin de chaque phase : tests verts, `README` mis à jour, commit, puis résumé en 5 lignes. Demande-moi validation avant la phase suivante.
4. Si une brique ne fonctionne pas sur Android, propose une alternative et **demande-moi** avant de changer l'architecture.
5. Commentaires et documentation en **français** ; identifiants de code en anglais.
6. **UX et performance sont des critères d'acceptation, pas des finitions** : chaque phase est refusée si elle dégrade les budgets de la section 11 ou les principes de la section 10.
7. **Chaque ajout doit justifier son poids** (Mo, mémoire, démarrage, batterie). En cas de doute, la solution la plus légère l'emporte.

---

## 1. Objectif fonctionnel

Projia est un **hub d'IA centralisé** (à la manière d'OpenRouter) qui :

| # | Exigence |
|---|----------|
| F1 | Choisit **automatiquement** le meilleur modèle **gratuit** en ligne adapté à la tâche du prompt. |
| F2 | **Bascule automatiquement** vers un autre modèle quand le quota est épuisé (429, quota journalier, erreur fournisseur), **sans perdre l'historique**. |
| F3 | **Revient** au meilleur modèle dès qu'il redevient disponible. |
| F4 | N'utilise **que des modèles gratuits** ; sinon, et seulement si l'utilisateur l'a autorisé, ses **comptes payants** (avec plafond de dépense). |
| F5 | Est **agentique** : boucle d'outils, client **MCP**, **recherche web** quand nécessaire. |
| F6 | **Dépend entièrement** des plateformes de classement et des catalogues de modèles en ligne. |
| F7 | Fonctionne en **deux modes** : autonome sur chaque appareil (Linux, Android) **et** mode client-serveur (Android → serveur Linux), avec synchronisation optionnelle de l'historique. |
| F8 | **Choix manuel facultatif** : l'utilisateur peut fixer le modèle qu'il préfère (globalement, par conversation ou par catégorie de tâche) **ou** laisser le mode « Auto ». Les deux coexistent (section 4.3). |
| F9 | **Veille et auto-configuration** : l'application suit les nouveautés (nouveaux modèles, nouveaux modèles gratuits, changements de quotas, modèles retirés) et **met à jour son catalogue à chaque utilisation**, sans intervention (section 3bis). |
| F10 | **Complet pour tout type de tâche IA** : texte, image (génération/édition, vision/OCR en entrée), son (transcription, synthèse vocale, musique/effets si gratuits), vidéo — avec la **même logique** auto / bascule / retour / gratuit d'abord (section 3ter). |
| F11 | **Interface très épurée et intuitive**, expérience utilisateur optimale (section 10). |
| F12 | **Ultra légère et performante**, gratuite : budgets mesurés et vérifiés en CI (section 11). |
| F13 | **Une release GitHub par version**, automatisée (section 12). |

---

## 2. Pile technique imposée

- **Cœur (`projia-core`)** : Python ≥ 3.11 (vérifier la version supportée par serious_python sur Android), `asyncio`, `httpx`, `pydantic`, `SQLite` (via `aiosqlite`).
- **Routage / appel des fournisseurs** : **LiteLLM** (Router, fallbacks, cooldowns) côté Linux. **Vérifie en phase 1 que LiteLLM s'embarque sur Android** ; s'il est trop lourd (dépendances natives), écris un adaptateur minimal OpenAI-compatible en `httpx` derrière la même interface `ProviderClient`.
- **Serveur (mode Linux / client-serveur)** : FastAPI exposant une API **compatible OpenAI** (`/v1/chat/completions`, `/v1/models`) + WebSocket pour le streaming et les événements de bascule.
- **Interface** : **Flutter** (Android + Linux desktop).
- **Python embarqué dans Flutter** : `serious_python` (Flet) — le cœur tourne dans un thread d'arrière-plan et expose l'API sur `127.0.0.1` ; l'UI Flutter parle à `localhost` (mode local) ou au serveur distant (mode client-serveur) **avec le même code**.
- **MCP** : SDK Python officiel `mcp` dans le cœur (clients stdio sur Linux ; **Streamable HTTP uniquement sur Android**, pas de lancement de processus).
- **Recherche web gratuite** : `ddgs` (métarecherche sans clé API) + outil `fetch_url` (extraction texte avec `trafilatura` ou équivalent léger).
- **Secrets** : `flutter_secure_storage` (Android Keystore) et `keyring`/fichier chiffré sur Linux. Aucune clé en clair dans SQLite ni dans les logs.

---

## 3. Sources de données en ligne (F6)

Crée un module `catalog/` avec un **fetcher par source**, un cache local (TTL configurable, défaut 6 h) et un mode dégradé (dernier cache valide si hors ligne).

| Source | Usage | Remarques à vérifier |
|---|---|---|
| **OpenRouter** `GET https://openrouter.ai/api/v1/models` | Catalogue, prix (`pricing.prompt == "0"` ⇒ gratuit, suffixe `:free`), `context_length`, `supported_parameters` (tools, vision…) | Pas de clé requise pour lister. Limites free : vérifier via `GET /api/v1/key`. |
| **Artificial Analysis** `GET https://artificialanalysis.ai/api/v2/data/llms/models` | Indices d'intelligence, **code**, **maths**, vitesse, latence | Clé gratuite (en-tête `x-api-key`), ~1000 req/jour, **attribution obligatoire** dans l'UI (« À propos »). |
| **LMArena** — dataset HF `lmarena-ai/leaderboard-dataset` | ELO par catégorie (text, code, vision…) | Licence CC BY 4.0 → attribution. |
| **cheahjs/free-llm-api-resources** (GitHub) | Découverte des autres fournisseurs gratuits (Google AI Studio, Groq, Cerebras, Mistral, GitHub Models, NVIDIA NIM, Cloudflare…) | Parser le README ; l'utilisateur fournit ses clés gratuites pour chacun. |

**Résolution d'identité des modèles** : écris `catalog/matcher.py` qui associe un même modèle entre sources (normalisation du nom, famille, taille, variante). Couvre-le par des tests sur des cas réels. Les modèles non appariés reçoivent un score par défaut prudent.

---

## 3bis. Veille des nouveautés et auto-configuration (F9)

Module `catalog/watcher.py` :

1. **Rafraîchissement à chaque utilisation** : à l'ouverture de l'app et avant chaque nouvelle conversation, lancer en arrière-plan une mise à jour **incrémentale** (non bloquante : on répond avec le cache, puis on applique la mise à jour au tour suivant).
2. **Détection des nouveaux modèles** :
   - OpenRouter : champ `created` (timestamp d'ajout) et tri `sort=newest` / filtre `max_age_days` de l'API Models (vérifier leur disponibilité) ;
   - flux RSS des nouveaux modèles et des annonces OpenRouter ;
   - diff entre le catalogue courant et le précédent (`new`, `removed`, `price_changed`, `became_free`, `no_longer_free`, `capabilities_changed`).
3. **Intégration automatique** : tout nouveau modèle est ajouté, apparié aux classements (matcher), puis classé. S'il n'a pas encore de score (trop récent pour AA/LMArena), lui attribuer un score provisoire à partir de sa famille/fournisseur et de la fiabilité observée ; le mettre à jour dès que les classements le couvrent.
4. **Retrait automatique** : un modèle retiré ou devenu payant sort de la chaîne gratuite ; si c'était le modèle préféré de l'utilisateur, le prévenir et proposer le meilleur équivalent.
5. **Quotas** : relire périodiquement les limites (ex. `GET /api/v1/key`) et la liste cheahjs pour ajuster `quota.py` sans mise à jour de l'app.
6. **Fil « Nouveautés »** dans l'UI : liste datée des changements (nouveau modèle gratuit, nouveau n°1 en code, modèle retiré…), avec option de notification.
7. **Auto-configuration au premier lancement** : détecter les fournisseurs pour lesquels l'utilisateur a une clé, construire le catalogue, choisir les poids par défaut — aucune configuration manuelle obligatoire.

---

## 3ter. Multimodalité : image, son, vidéo (F10)

### Fournisseurs gratuits candidats (à **revérifier au moment du codage** ; chiffres issus de sources secondaires)

| Modalité | Candidats gratuits | Remarques |
|---|---|---|
| **Image (génération)** | Pollinations (sans clé, débit limité) ; Cloudflare Workers AI (FLUX, quota quotidien en « neurons ») ; Hugging Face Inference Providers (crédits mensuels) ; Google Gemini (quota gratuit image **contradictoire selon les sources** → vérifier) | OpenRouter : au moment de la vérification, **aucun modèle image `:free`** → le traiter comme payant. |
| **Son — transcription (STT)** | Groq Whisper large-v3 / turbo (quota quotidien en requêtes **et** en secondes d'audio) ; Cloudflare Workers AI | Les quotas STT sont séparés des quotas texte. |
| **Son — synthèse vocale (TTS)** | Cloudflare / Google (à vérifier) ; **repli local gratuit** : synthèse vocale du système (Android TextToSpeech, Linux speech-dispatcher/espeak-ng ou Piper) | Le repli local garantit une fonction TTS toujours disponible et sans quota. |
| **Vidéo** | Crédits d'inscription (ex. fal.ai, montant variable) ; Spaces Hugging Face communautaires (Wan 2.2, ZeroGPU, files d'attente) | **Le gratuit est rare et instable** : traiter en « meilleur effort » (voir ci-dessous). Les poids ouverts (ex. Wan) sont inexécutables sur mobile. |
| **Découverte** | `cheahjs/free-llm-api-resources` + « Free LLM API Hub » (catégories image, speech, vision, embeddings) | Parser comme sources du catalogue (F9) pour détecter les nouveaux fournisseurs médias. |

### Architecture
- Interface `MediaProvider` : `submit(job) → job_id`, `poll(job_id)`, `fetch(job_id) → fichier`. Les jobs sont **persistés** (SQLite) et **asynchrones** : l'utilisateur peut quitter l'écran, une notification l'avertit à la fin.
- Mêmes mécanismes que le texte : classement par catégorie, `quota.py`, bascule, retour au meilleur, mode « Auto » ou modèle choisi, gratuit d'abord, plafonds payants (F4).
- **Vidéo en « meilleur effort »** : essayer les sources gratuites dans l'ordre ; si aucune n'est disponible, l'écrire clairement (« indisponible gratuitement pour le moment ») et proposer, sans l'imposer, un fournisseur payant avec plafond.
- Entrées : photo/caméra, fichier, micro (dictée), partage système vers Projia.
- Médias stockés **sur disque** (jamais en BLOB SQLite), avec miniatures, métadonnées (modèle, prompt, graine) et purge configurable.
- **Outils d'agent** : `generate_image`, `edit_image`, `transcribe`, `speak`, `generate_video` — l'agent peut les enchaîner (ex. transcrire → résumer → lire à voix haute).
- **Convention de contenu** : si un prompt d'image contient des équations ou du texte long, **prévenir** que les modèles d'image les rendent mal et proposer de produire la figure par code (SVG, matplotlib, TikZ) ou en LaTeX rendu dans le chat plutôt que dans l'image.

---

## 4. Sélection automatique du modèle (F1)

### 4.1 Classification de la tâche
`router/classifier.py` renvoie un `TaskProfile` :
- `category` ∈ {chat, code, math, reasoning, writing, translation, vision, long_context, agentic/tool_use, search} **et médias** : {image_gen, image_edit, stt, tts, music_sfx, video_gen} (section 3ter)
- `modality` d'entrée/sortie déduite du prompt (« dessine… », « lis à voix haute », « transcris », « anime cette image ») **sans que l'utilisateur ait à choisir un mode**.
- besoins : `needs_tools`, `needs_vision`, `min_context` (taille réelle de l'historique + marge), `latency_pref`.

Deux étages : (1) heuristiques rapides (blocs de code, LaTeX, pièces jointes images, longueur, mots-clés FR/EN/MG) ; (2) si ambigu, appel à un **petit modèle gratuit rapide** avec sortie JSON. Mettre en cache par conversation.

### 4.2 Score
Pour chaque modèle **éligible** (capacités compatibles, contexte suffisant, non en cooldown) :

```
score = w_q · Qualité(category) + w_s · Vitesse + w_r · Fiabilité − pénalités
```
- `Qualité` : indice AA correspondant (code/maths/intelligence) et/ou ELO LMArena de la catégorie, normalisés dans [0,1].
- `Fiabilité` : taux de succès observé localement (fenêtre glissante).
- Poids dans `config.yaml`, modifiables dans l'UI.
- Ordre de coût strict : **gratuit > payant**. Un modèle payant n'entre dans le classement que si F4 l'autorise.

Sortie : liste ordonnée `[m1, m2, …]` = chaîne de repli. Afficher dans l'UI le modèle choisi et **pourquoi** (catégorie + score).

### 4.3 Choix manuel (F8)
- Sélecteur de modèle dans l'UI : **« Auto »** (défaut) ou un modèle précis, avec recherche, filtres (gratuit, code, vision, outils) et score affiché.
- Portées : **global**, **par conversation**, **par catégorie** (ex. « toujours tel modèle pour le code »).
- Un modèle choisi manuellement passe **en tête** de la chaîne ; la chaîne de repli automatique reste derrière lui.
- Si le modèle préféré est épuisé : bascule automatique (section 5) puis **retour à ce modèle préféré** (pas au n°1 du classement) dès qu'il est disponible. Option « strict » : attendre/avertir au lieu de basculer.
- Bouton « Revenir en Auto » à tout moment ; le choix est mémorisé.

---

## 5. Bascule et retour (F2, F3)

### 5.1 Historique canonique
- Stocker chaque conversation dans SQLite au **format OpenAI canonique** (messages, tool_calls, tool results, pièces jointes référencées), indépendant du fournisseur.
- Chaque message garde la trace du modèle qui l'a produit.

### 5.2 Gestionnaire de quotas (`router/quota.py`)
- États par (fournisseur, modèle, clé) : `available`, `cooldown(until)`, `exhausted_daily(until)`.
- Sur 429 / erreur de quota : lire `Retry-After`, en-têtes `x-ratelimit-*`, ou `/api/v1/key` (OpenRouter) pour fixer `until` ; sinon backoff exponentiel plafonné.
- Compteurs locaux RPM/RPD pour **anticiper** l'épuisement (ne pas attendre le 429).

### 5.3 Bascule en cours de conversation
1. Échec du modèle courant → modèle suivant de la chaîne.
2. **Adaptation de l'historique** si le nouveau modèle a un contexte plus petit : garder system + derniers tours, résumer les anciens tours avec un modèle gratuit, conserver le résumé en base.
3. Adapter les messages d'outils si le modèle cible ne supporte pas le format natif (dégradation en texte).
4. Si la bascule survient **pendant un streaming**, relancer la génération sur le nouveau modèle à partir du dernier message utilisateur (ne pas concaténer des réponses partielles) et le signaler dans l'UI.
5. Événement `model_switched` (ancien, nouveau, raison) envoyé à l'UI.

### 5.4 Retour au meilleur modèle
- **À chaque nouveau tour**, recalculer le classement : si un modèle mieux classé est sorti de cooldown, il est réutilisé automatiquement.
- Ne **jamais** « sonder » un modèle avec des requêtes de test (cela consomme le quota gratuit).
- Notification discrète : « Retour à <modèle> ».

---

## 6. Comptes payants (F4)

- L'utilisateur saisit ses clés (OpenRouter, Anthropic, OpenAI, Google…) dans l'UI ; stockage sécurisé uniquement.
- Réglages : `paid_fallback = off | ask | auto`, **plafond quotidien et mensuel**, liste des modèles payants autorisés.
- Mode `ask` : l'UI demande confirmation avant le premier appel payant de la conversation, en affichant le coût estimé.
- Journal de dépenses local (tokens × prix du catalogue).

---

## 7. Agent, outils, MCP, recherche web (F5)

- **Boucle agentique** (`agent/loop.py`) : plan → appel d'outil → observation → réponse, avec limite d'itérations et de temps configurables.
- **Outils natifs** : `web_search` (ddgs), `fetch_url`, `calculator` (sympy), `read_file`/`write_file` limités à un dossier de travail.
- **Décision de recherche web** : le modèle décide via l'outil ; en plus, le classifieur force la recherche si la question porte sur l'actualité ou des données récentes. Les réponses issues du web **citent leurs URL**.
- **MCP** : gestion des serveurs dans `mcp_servers.yaml` (nom, transport, URL/commande, activé). Les outils MCP sont fusionnés avec les outils natifs. Sur Android : serveurs distants en Streamable HTTP uniquement.
- **Choix du modèle pour l'agent** : si des outils sont nécessaires, ne retenir que les modèles avec `tools` dans `supported_parameters`.
- **Sécurité** : confirmation de l'utilisateur pour tout outil à effet de bord ; le contenu web/MCP est traité comme donnée, jamais comme instruction (protection contre l'injection de prompt).

---

## 8. Phases de développement

| Phase | Livrable | Critère d'acceptation |
|---|---|---|
| **1. Fondations** | Structure du dépôt, CI (ruff, mypy, pytest), config, SQLite ; **preuve de concept serious_python + httpx sur Android** | APK de test qui fait un appel HTTP depuis Python embarqué ; **taille réelle et temps de démarrage mesurés** ; budgets fixés ; décision de la section 11 si dépassement. |
| **2. Catalogue & veille** | Fetchers OpenRouter / AA / LMArena / cheahjs, cache, matcher, `watcher.py` (diff, RSS, nouveaux modèles) | `projia catalog list --free --category code` affiche un classement cohérent ; un modèle ajouté côté source apparaît sans redémarrage. |
| **3. Routeur** | Classifieur, score, chaîne de repli, choix manuel (global / conversation / catégorie) | Tests : un prompt de code choisit un modèle bien classé en code ; un modèle préféré passe en tête. |
| **4. Quotas & bascule** | `quota.py`, adaptation d'historique, retour au meilleur | Test d'intégration avec faux fournisseur renvoyant 429 : conversation continue, historique intact, retour après cooldown. |
| **5. API serveur & médias** | FastAPI OpenAI-compatible (`/v1/chat/completions`, `/v1/images/generations`, `/v1/audio/transcriptions`, `/v1/audio/speech`) + WebSocket ; `MediaProvider` et jobs asynchrones (image, STT, TTS, vidéo meilleur effort) | Un client OpenAI standard fonctionne en pointant sur Projia ; une image et une transcription gratuites passent par la même bascule que le texte. |
| **6. Agent & MCP** | Boucle, outils natifs, client MCP, ddgs | Question d'actualité → recherche web → réponse sourcée. |
| **7. UI Flutter** | **2 maquettes à valider d'abord**, puis : chat épuré, sélecteur « Auto / modèle préféré », galerie Créations, fil « Nouveautés », bandeaux de bascule, réglages Simple/Avancé, écran « À propos » avec attributions (section 10) | Fonctionne sur Linux desktop, téléphone et tablette ; budgets de la section 11 respectés. |
| **8. Deux modes + sync** | Mode local / distant, synchronisation optionnelle de l'historique | Même conversation visible sur les deux appareils. |
| **9. Paiement & finitions** | Comptes payants, plafonds, journal de dépenses, optimisation (taille, démarrage, mémoire) | Aucun appel payant sans autorisation ; plafond respecté ; budgets tenus. |
| **10. Releases GitHub** | Workflows Actions, signature, AppImage + APK par ABI, `SHA256SUMS`, CHANGELOG, `RELEASING.md`, vérification de mise à jour dans l'app | `git tag v0.1.0` produit automatiquement une release complète. |

---

## 9. Arborescence attendue

```
projia/
├── core/                 # Python
│   ├── catalog/          # fetchers, cache, matcher
│   ├── router/           # classifier, scoring, quota, fallback
│   ├── providers/        # LiteLLM ou adaptateur httpx
│   ├── agent/            # loop, tools, mcp
│   ├── media/            # MediaProvider : image, stt, tts, video, jobs async
│   ├── storage/          # SQLite, historique canonique
│   ├── server/           # FastAPI
│   └── tests/
├── app/                  # Flutter (android + linux)
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SOURCES.md        # docs consultées + date de vérification
│   └── ATTRIBUTIONS.md   # Artificial Analysis, LMArena (CC BY 4.0)…
├── .github/workflows/    # CI + release automatique (section 12)
├── config.example.yaml
└── README.md
```

---

## 10. Interface et expérience utilisateur (F11)

### Principes d'épure
- **Un écran principal** : conversation + champ de saisie. Rien d'autre n'est visible par défaut.
- Barre de saisie : champ, bouton **« + »** (fichier, photo, micro, forcer un type de média), envoi. Une **puce discrète « Auto ▾ »** ouvre le sélecteur de modèle (F8).
- **Pas de « mode » à choisir** : la modalité est détectée (section 4.1) ; le bouton « + » ne sert qu'à forcer.
- **Divulgation progressive** : seulement 3 destinations — **Chat** (historique en tiroir), **Créations** (galerie image/son/vidéo), **Réglages** (onglets *Simple* / *Avancé*). Tout fonctionnalité courante en **≤ 3 appuis**.
- **Résultats intégrés à la conversation** : image zoomable, lecteur audio, lecteur vidéo, partage/téléchargement en 1 appui.
- **Transparence légère** : puce du modèle utilisé ; « pourquoi ce modèle ? » au toucher. Bascule et retour (F2/F3) = **bandeau discret non bloquant**, jamais une fenêtre modale.
- **Zéro configuration obligatoire** : onboarding de **3 écrans maximum, passable** ; guide d'ajout de clés gratuites avec liens directs et **validation immédiate** de la clé ; mode sans clé si des fournisseurs sans clé sont disponibles.
- **États soignés** : vide (3 suggestions cliquables), chargement (squelettes, pas de spinner plein écran), hors ligne (cache + message clair), erreur (phrase humaine + **une** action).
- **Rendu riche** : Markdown, tableaux, code avec bouton copier, **LaTeX pour les mathématiques**, streaming fluide sans saccades.

### Consignes de conception reprises de mes projets précédents (plateforme de tutorat)
- Design **Material You / Fluent** ; palette douce et professionnelle : **bleu indigo + vert menthe + blanc cassé**.
- **Mode clair / sombre** (suivre le système par défaut).
- Navigation : **barre d'onglets en bas (mobile)** et **barre latérale (desktop / tablette)** — mise en page adaptative.
- **Micro-animations** et transitions fluides, sobres (< 200 ms), avec option « réduire les animations ».
- **Accessibilité** : tailles de police ajustables, contraste **WCAG AA**, cibles tactiles ≥ 48 dp, navigation clavier complète.
- **Recherche globale** (conversations + créations) avec filtres.
- **Notifications intelligentes** : seulement l'utile (fin d'une tâche vidéo longue, nouveau modèle gratuit si activé), regroupées, désactivables.
- Application **en français par défaut** ; internationalisation prête (fr, en, mg).
- Linux : raccourcis (Ctrl+Entrée pour envoyer, Ctrl+K recherche) ; appareils de test : Linux KDE, téléphone Android, tablette.

### Méthode
- **Avant de coder l'UI (phase 7)** : propose 2 maquettes/wireframes de l'écran principal (mobile + desktop) et attends mon choix.
- Chaque écran est revu contre cette section avant de passer à la suite.

---

## 11. Performance et légèreté (F12)

Les cibles ci-dessous sont des **objectifs initiaux** : mesure-les dès la phase 1, publie les valeurs réelles dans le README et fixe des **budgets** appliqués par la CI (le build échoue en cas de dépassement).

| Axe | Objectif / règle |
|---|---|
| **Taille** | APK **découpé par ABI**, minification/R8, ressources compressées ; budget chiffré en phase 1 après mesure. |
| **Dépendances** | Aucune bibliothèque lourde inutile (pas de numpy/pandas/torch), **aucun modèle embarqué**, imports paresseux, modules médias chargés à la demande. |
| **Démarrage** | UI interactive en **< 2 s à froid** sur un téléphone de milieu de gamme ; le cœur Python démarre en arrière-plan sans bloquer l'UI. |
| **Fluidité** | 60 fps, taux de saccades < 1 % (Flutter DevTools). |
| **Latence** | Surcoût Projia **< 100 ms** avant l'envoi au fournisseur ; sélection du modèle **< 20 ms** (scores en mémoire). |
| **Mémoire** | Listes virtualisées, images décodées à la taille d'affichage, miniatures, pagination de l'historique. |
| **Réseau** | Connexions réutilisées, compression, cache conditionnel (ETag) des catalogues, mises à jour incrémentales, **pas de polling agressif**. |
| **Batterie** | Aucun service permanent ni wake lock ; tâches longues (vidéo) en arrière-plan avec notification. |
| **Stockage** | SQLite en mode WAL avec index ; médias sur disque avec quota et purge. |
| **Mesure continue** | Banc d'essai CI : taille des artefacts, temps de démarrage, mémoire ; rapport joint à chaque release. |

**Point de décision (phase 1).** Un runtime Python embarqué alourdit l'APK. Si le budget de taille est dépassé, **arrête-toi et propose-moi** : (a) un cœur Dart léger pour Android avec le même contrat d'API, Python restant pour Linux/serveur ; ou (b) Android en client léger vers un serveur. Ne tranche pas seul.

---

## 12. Dépôt GitHub et releases (F13)

- Dépôt public `projia`, licence **MIT**, versionnement **SemVer**, commits **Conventional Commits**, `CHANGELOG.md` (format *Keep a Changelog*).
- **Une GitHub Release par version** (tag `vX.Y.Z`), créée par **GitHub Actions** : APK signés (par ABI), AppImage (Flatpak en option), `SHA256SUMS` (+ signature), notes de version générées depuis le CHANGELOG, rapport de taille/performance.
- CI à chaque PR : lint, typage, tests, budgets de la section 11 ; **une release est bloquée si un contrôle échoue**.
- **Secrets de signature** : jamais dans le dépôt. Documente la procédure dans `docs/RELEASING.md` et **dis-moi quels secrets créer** dans GitHub.
- **Mise à jour dans l'app** : vérification non bloquante de la dernière release via l'API GitHub, notification, ouverture de la page ; **aucune installation silencieuse**.
- Fichiers communautaires : `README` (captures, installation), `CONTRIBUTING`, `SECURITY`, `CODE_OF_CONDUCT`, modèles d'issues, `ATTRIBUTIONS`. Publication F-Droid étudiée ensuite.

### Conformité des fournisseurs
- **Clés personnelles uniquement (BYOK)** : chaque utilisateur utilise ses propres clés ; **aucun proxy avec clé partagée**. Certaines CGU interdisent la revente d'accès ou la création d'un service concurrent (ex. OpenRouter, selon une source secondaire à vérifier) et certains fournisseurs ont des restrictions régionales (ex. Google AI Studio dans l'EEE/CH/UK, idem).
- Consigne les CGU de chaque fournisseur dans `docs/COMPLIANCE.md` avec la date de vérification.

---

## 13. Contraintes non négociables

- Gratuit et open source ; aucun service payant requis pour fonctionner.
- Aucune donnée de classement ou quota codée en dur.
- Aucun appel payant sans autorisation explicite.
- Historique jamais perdu lors d'une bascule.
- Respect des conditions d'utilisation de chaque fournisseur et des attributions obligatoires.
- Tests automatisés pour le routeur, les quotas et la bascule (fournisseurs simulés).
- Tout type de tâche (texte, image, son, vidéo) soumis aux mêmes règles : gratuit d'abord, bascule, retour, historique conservé.
- Interface épurée : pas de fonctionnalité ajoutée si elle alourdit l'écran principal.
- Budgets de taille et de performance respectés et vérifiés en CI.
- Une release GitHub signée et documentée par version.
- Clés personnelles uniquement, aucune clé partagée.

**Commence par la phase 1** : propose l'arborescence, le `pyproject.toml`, le `pubspec.yaml` et le plan de la preuve de concept Android, et les budgets de taille/performance à mesurer, puis attends ma validation.
