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
- [x] Dépôt public `raantss18/tontolo`, tag `v0.1.0`, release vérifiée

## Après v0.1.0
- [ ] Publication F-Droid (à étudier)
- [ ] Flatpak (optionnel)
- [ ] Tester sur un vrai téléphone et une tablette

## v0.2.0 — demandes du 2026-10-10
- [x] Bug : la lecture vocale ne peut pas être arrêtée (lecture/arrêt, vitesse)
- [x] Fonctions inspirées des meilleurs outils (ChatGPT, Claude, Open WebUI, LibreChat, Jan) :
      régénérer, modifier et renvoyer, instructions personnalisées, export/partage Markdown,
      conversations épinglées, raccourcis « / » (modèles de prompts)
- [x] Mémoire à long terme locale avec compactage automatique
- [x] Compatibilité Android 10 (API 29) → dernière version, testée sur émulateur API 29 et 36
- [x] Audit de sécurité et corrections (CSRF/DNS rebinding, SSRF, épinglage des fournisseurs,
      liens, calculatrice, MCP distant, journaux, mises à jour)
- [ ] Tests, CI, push GitHub, release v0.2.0

- [x] Bascule sans clé : Kilo Code, LLM7, OVHcloud (signalé le 2026-10-10)

## v0.2.3 — signalements du 2026-10-10 (après la 0.2.2)
- [x] « crée la photo » non reconnu comme demande d'image → détection élargie + demandes de suite
- [x] Historique `[média:…]` pris pour des espaces réservés par les modèles de texte
- [x] Bascule automatique vers la génération d'image quand un modèle de texte refuse
- [x] **Retouche de photo qui ne suit pas la consigne** (« sans changer la personne ni la composition » → une autre personne était générée) :
  - [x] Retouche locale fidèle sur l'appareil (lumière, contraste, netteté, couleurs, noir et blanc, sépia, vintage, « professionnel »…) — gratuite, privée, hors ligne
  - [x] Route d'envoi : consigne de fidélité ou retouche simple → locale ; transformation créative → réinterprétation (avec avertissement)
  - [x] Ne jamais générer une autre personne quand l'utilisateur demande de la conserver : message honnête + alternatives
  - [x] Endpoint cœur pour enregistrer un résultat de retouche locale (historique, galerie, mode distant)
  - [x] Tests (cœur + Dart), documentation (vie privée : la photo n'est envoyée à aucun service pour la retouche locale)
- [x] Publier la 0.2.3 (CI verte, release, vérification)

## Demande de contenu pour un post
- [x] Captures d'écran Android (émulateur API 36) : accueil, réponse avec formules, pourquoi ce modèle, sélecteur de modèle, image, réglages/clés, mémoire, retouche, mode sombre, nouveautés
- [x] Captures d'écran Linux (application de bureau)
- [x] Courtes vidéos de démonstration (≈ 30 s) : chat + formules, génération d'image, retouche de photo ; version Android et bureau
- [x] Visuels prêts pour un post (cadres, légendes), dossier `press/` + captures dans `docs/screenshots/`
- [x] Publier la 0.2.4 (correctifs trouvés pendant les prises de vue)

## v0.2.5 — Coupure réseau (retour d'un utilisateur)
- [x] Détecter « appareil hors ligne » (sonde) et ne pas défiler les modèles ni les pénaliser
- [x] Attente du retour du réseau puis reprise avec le même modèle ; message clair sinon
- [x] Interface : bascules regroupées sur une ligne, statut « en attente du réseau »
- [x] Tests (3) et publication

## Priorités immédiates (retours utilisateur du 2026-10-11) — avant la suite de la feuille de route
- [x] P1. Bug : « Manaova sary tilikambo jiro » → « Aucune source gratuite disponible pour ce type de média » (création d'image en malgache / source d'images indisponible)
- [x] P2. Bouton « Régénérer / Réessayer » sur toute réponse en échec (média ou texte), comme sur la capture
- [x] P3. Langues : anglais et malgache complets dans l'application (aucune chaîne française restante, messages du cœur traduits), questions à l'utilisateur pour les termes malgaches difficiles
- [x] P4. Notification quand un modèle (ou la création d'image/vidéo) redevient disponible après une pause ou un quota épuisé

## Priorités (retours utilisateur du 2026-10-11, 2e lot)
- [x] Q1. Bug : « Draw a woman wearing gucci » → modèle texte qui prétend avoir créé l'image ; détecter « draw/sketch/paint » et basculer vers l'image quand un modèle texte prétend avoir généré une image
- [x] Q2. Raisons de bascule traduites (« problème réseau » affiché en anglais/malagasy)
- [x] Q3. Termes malagasy validés par l'utilisateur : Kirakira (réglages), Fanalahidy (clé), Horonan-tsary, Fetra, Fampandrenesana, Mandeha ho azy (auto), Matihanina, Fintinina (résumer), impératif
- [x] Q4. Crédits de l'auteur partout (À propos, crédits, notes de chaque mise à jour, README) : RANIRIAMANJAKA Antsa · github.com/raantss18 · antsa.raniriamanjaka@univ-antananarivo.mg · +261 33 43 838 82
- [~] Q5. Statistiques d'utilisation (Supabase choisi, activées par défaut et désactivables) : application, SQL et doc prêts ; en attente du projet Supabase de l'utilisateur (variables STATS_URL / STATS_ANON_KEY)
- [x] Q6. Audit de sécurité complet + corrections
- [ ] Q7. Vérifier à nouveau la compatibilité de mise à jour (0.2.0 → dernière) à chaque version

## Feuille de route 2026-10 (validée par l'utilisateur, dans l'ordre, étape par étape)
Règle : chaque étape est livrée seule (tests verts, rien de cassé), puis publiée.

- [x] 0. v0.2.6 — Navigation : Discussion / Créations / Réglages dans le volet des discussions (barre du bas supprimée sur mobile, flèche de retour) ; vérifier sur émulateur
- [x] 0b. Play Protect : documenter (README/INSTALL) pourquoi l'alerte apparaît et comment l'éviter (vérification développeur Google / Play Console, à faire par le propriétaire du compte)
- [x] V. Vidéo : essai de faisabilité (Pollinations vidéo = payant uniquement ; Space officiel LTX-Video = gratuit sans clé, quota ZeroGPU quotidien) ; texte → vidéo et photo → vidéo branchés, lecture dans l'application, message clair sur le quota
- [x] 1. Écran vide interactif : raccourcis (image, retouche, recherche web, résumer un document, traduire, expliquer)
- [x] 2. Sélecteur de modèle : « Auto » + pastille de santé (vert/orange/rouge), appui long pour fixer un modèle
- [x] 3. Réponse rapide d'abord (petit modèle rapide, puis relève par le meilleur si complexe) — option
- [x] 4. File d'attente hors ligne : message mis en attente et envoyé au retour du réseau
- [x] 5. Page « État des modèles » : disponibles / en pause / épuisés, heure de retour
- [x] 6. Modèles locaux (Ollama ; GGUF sur Linux) comme dernier recours sans réseau
- [x] 7. Documents : PDF / page web → questions avec citations des passages
- [x] 8. Dossiers de discussions + recherche plein texte
- [~] 9. Partage d'une discussion : page web faite (0.2.11) ; image d'une réponse à faire
- [ ] 10. Dictée vocale + mode conversation mains libres
- [ ] 11. Design : thème coloré enfantin-sérieux aligné sur le logo (palette, typographie, animations légères)
- [ ] 12. Android : widget d'écran d'accueil + raccourci « Demander à Tontolo »
- [ ] 13. Tablette / bureau : volet permanent + deux colonnes (discussion / aperçu)
- [x] U. Mises à jour : repli sans API GitHub (limite de débit), résultat toujours affiché, notes et nouveautés cumulées des versions sautées, CI de compatibilité depuis 0.2.0, test de base 0.2.0
- [ ] Transversal : plus d'interactivité (suggestions de relance après chaque réponse, actions rapides sur les messages, retours haptiques, animations)

## v0.3.0 — demandes du 2026-10-11 (3e lot, version majeure)
Ordre : retours d'utilisateurs d'abord, puis nouvelles fonctions ; rien de cassé, saut de mise à jour vérifié.
- [x] R0. Vérifier la base Supabase des statistiques (insertion OK, lecture refusée à la clé publique, contrôles actifs)
- [x] R1. Bug utilisateur : continuer dans Tontolo une discussion venant d'un lien Claude (claude.ai/share/…) ; aussi ChatGPT, Gemini, texte collé
- [x] R2. À chaque message, réévaluer le meilleur modèle selon le contexte de la discussion (pas de modèle « collé » à la conversation)
- [x] R3. Création d'image : ne plus rester bloqué sur Pollinations, choisir la meilleure source d'image disponible
- [x] F1. Aide par fournisseur d'API : étapes simples et lien direct pour obtenir la clé (fr/en/mg)
- [x] F2. Réglages simplifiés : proposer les serveurs d'API payants avec plafond de dépense (simple)
- [ ] F3. Mode Apprendre (élèves / étudiants), inspiré de Khanmigo, MagicSchool, MIA Seconde, Dinobot : bascule Général / Apprendre bien visible, niveau scolaire, guidage pas à pas sans donner la réponse, indices, quiz interactifs, fiches, correction d'exercice en photo, plan de révision
- [~] F4. Comptes (Google / GitHub) et synchronisation entre appareils : discussions, mémoires, clés d'API (chiffrées de bout en bout)
- [x] F5. Guide de publication : Play Store, F-Droid, dépôts Linux (Flathub, AUR, Snap, .deb)
- [ ] F6. Audit de vulnérabilités + compatibilité de saut de mise à jour (0.2.0 → 0.3.0) sur émulateur
- [ ] F7. Publier la 0.3.0
