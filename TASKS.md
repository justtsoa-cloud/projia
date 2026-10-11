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
- [x] Q5. Statistiques d'utilisation (Supabase) : projet créé par l'utilisateur, connexion vérifiée le 2026-10-11 ; actives à partir des builds 0.3.0
- [x] Q6. Audit de sécurité complet + corrections
- [x] Q7. Compatibilité de mise à jour vérifiée pour la 0.3.0 (émulateur : 0.2.0 officielle → 0.3.0 par-dessus, discussion et mémoire conservées) — à refaire à chaque version

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
- [~] F4. Comptes et synchronisation chiffrée : code, tests, SQL et doc faits ; Supabase configuré le 2026-10-11 (table sync_items + RLS vérifiées, URL de retour localhost:43823, **connexion GitHub active**) ; reste : Google (facultatif), essai de connexion réel sur téléphone par l'auteur, relecture du protocole par Codex
- [x] F5. Guide de publication : Play Store, F-Droid, dépôts Linux (Flathub, AUR, Snap, .deb)
- [x] F6. Audit de vulnérabilités + compatibilité de saut de mise à jour (0.2.0 → 0.3.0) sur émulateur
- [x] F7. Publier la 0.3.0
- [x] Collaboration : ChatGPT/Codex en vérification indépendante (canal docs/collaboration/, hors dépôt) ; F5 repris par Claude après la limite d'usage de Codex

## v0.4.0 — demandes du 2026-10-11 (4e lot) : créations de fichiers et équipe de modèles
- [x] D1. Générer des fichiers : DOCX (Word), LaTeX compilé en PDF, carte mentale (image précise, pas une image d'IA) pour les révisions
- [x] D2. Vérifier puis corriger avant de livrer : compilation sans erreur (journal LaTeX renvoyé au modèle), contrôle du rendu (modèle de vision sur l'image), relecture du contenu ; jusqu'à 3 corrections
- [x] D3. Services de création gratuits et anonymes, choisis automatiquement avec repli (compilateurs LaTeX en ligne, Kroki pour les schémas), sans compte ni clé
- [x] D4. Équipe de modèles (agentique) : plusieurs modèles mobilisés pour une même demande complexe (rédacteur, relecteur d'une autre famille, correction), choisis par le routeur
- [x] D5. Interface : carte « fichier » dans la discussion (ouvrir, partager, enregistrer), fichiers dans Créations, étapes visibles (« compilation… », « vérification du rendu… »)
- [x] D6. Tests, émulateur, saut de mise à jour, publication 0.4.0
- [x] D7. Tout type de fichier à la demande (par défaut, gratuit) : DOCX, PDF/LaTeX, XLSX, PPTX, CSV, HTML, Markdown, code, SVG/schémas, cartes mentales, graphiques ; outils payants branchables si l'utilisateur a une clé
- [x] L1. Mode Apprendre plus simple : accueil épuré (niveau + une question), guidage strict sans réponse directe (« prochaine étape » au lieu de « solution »)
- [x] S1. Statistiques Supabase : collecte active et accès en lecture protégés, vérifiés le 2026-10-11.

## Retours utilisateur du 2026-10-11 (vidéo) — prioritaires
- [x] B1. Photo + « Put this on a public space in Antananarivo » : demande de modification d'image non reconnue (verbes « put / place / add… ») → envoyée à un modèle de texte
- [x] B2. La photo jointe clignote dans la bulle (décodage à chaque reconstruction)
- [x] B3. « Anime-la » après une image générée : la vidéo doit partir de cette image (pas du texte seul)
- [x] B4. « Rajoute des détails et des exemples » après une carte mentale : modifier le fichier existant (même format, source précédent repris), pas une réponse texte
- [x] B5. Photo d'exercice + « traite l'exercice 8… rends la réponse en pdf » → retouche d'image absurde : une tâche sur le CONTENU de la photo (exercice, question, résous…) n'est jamais une retouche ; photo + demande de fichier → transcription de la photo puis création du fichier
- [x] B6. Question simple (« sites pour créer des portfolios ? ») → « Nombre maximal d'étapes atteint » : le modèle enchaîne les recherches ; au dernier tour, répondre sans outil avec ce qui a été trouvé, et ne pas répéter un même appel d'outil
- [x] P1. Persistance du fil (signalé le 2026-10-11 : réponse à l'exercice d'une autre discussion) : priorités fil > dossier > mémoire, mémoire filtrée, résumé du fil en arrière-plan, photos anciennes allégées — v0.4.6
- [x] V1. Publicité 60 s verticale en anglais, musique jazz originale (press/campaign-v04/)

## Reprise Codex — authentification Google (2026-10-11)
- [x] Lire les derniers commits (base e5ab90a), la checklist et les transmissions de Claude ; arbre propre avant intervention.
- [x] Vérifier le flux existant : OAuth Supabase avec PKCE et retour local http://localhost:43823/.
- [x] Accéder au projet Google Cloud et au projet Supabase existants (connexion propriétaire effectuée).
- [x] Configurer le consentement et le client OAuth Web Google avec le callback exact du projet Supabase ; conserver GitHub. Configuration créée et secret enregistré par le propriétaire.
- [x] Activer Google dans Supabase, sans placer le secret OAuth dans le dépôt ou dans l’application. Google et GitHub ENABLED vérifiés ; retour http://localhost:43823/ autorisé ; dossier de clés ignoré et permissions privées.
- [ ] Tester connexion, annulation, retour Android/Linux, déconnexion et reconnexion ; vérifier GitHub également.
- [ ] Relire le protocole de synchronisation séparément et vérifier la conservation des données.
- [ ] Réconcilier les anciennes cases non cochées (publication 0.2.0, F3 Apprendre) avec les preuves de livraison ; ne pas les considérer automatiquement comme fonctionnalités absentes.

- [ ] Google reste en statut Testing sans utilisateurs de test : ajouter un testeur autorisé avant essai ; compléter présentation/confidentialité avant publication publique.
- [x] Tests ciblés PKCE et synchronisation : 5 tests réussis ; ne constitue pas un essai OAuth réel Android/Linux.

## v0.4.7 — retour Google/GitHub sur Android
- [x] Remplacer le serveur localhost Android par un lien natif vers Tontolo, sans nouvelle dépendance.
- [x] Conserver le PKCE temporaire dans le stockage sécurisé pour reprendre après redémarrage ; délai et suppression après usage.
- [x] Valider le lien reçu, ignorer les retours sans demande, empêcher les doubles échanges.
- [x] Ajouter le retour Android exact dans Supabase avec accord du propriétaire ; conserver le retour Linux et anciennes versions.
- [x] Tests : 192 cœur, 45 Flutter, analyse Flutter sans erreur ; dernier ajustement revérifié (analyse et 9 tests ciblés).
- [x] Trois APK signés construits ; installation par-dessus sur émulateur réussie (0.4.7, versionCode 4022), lien natif rouvre MainActivity à chaud et à froid.
- [x] Publication GitHub v0.4.7 (workflow 38162162769 réussi), fichiers présents et téléchargements en tête des notes ; SHA-256 de l’APK officiel x86_64 vérifié et installation par-dessus réussie.
- [ ] Essai Google réel par le propriétaire : configuration Google en mode Testing à vérifier si accès refusé.


## v0.5.0 — isolation du contexte et continuité des médias (Codex)
- [x] R1. Dossiers : organiser sans injecter les réponses des autres fils.
- [x] R2. Mémoire : séparer capture explicite globale et capture automatique du fil ; préserver la provenance et sérialiser le compactage.
- [x] R3. Médias : référence dans le fil courant, sans réutiliser une ancienne image après un échec ; animation avec photo jointe et consignes de mouvement.
- [x] R4. Tests de frontières et de régénération, résumés et conservation des données.
- [x] R5. 203 tests cœur et 47 Flutter ; analyses/typage propres ; release v0.5.0 publiée (workflow 38166719297 réussi), APK officiel SHA-256 vérifié et installation sans effacement réussie.

- [ ] R6. Vérifier visuellement une vidéo réelle quand le quota LTX revient : l’essai réel du 2026-10-11 atteint le service mais reçoit « quota GPU gratuit épuisé ». Le code, l’image source exacte, le mode Gradio et les reprises sont testés avec fournisseurs simulés.
