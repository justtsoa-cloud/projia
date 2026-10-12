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
- [x] Essai émulateur : cache (« Efa novaliana… », réponse instantanée), écran avancé (fournisseurs, exclusions, enchaînement ajouté puis retiré, délais) OK ; date du cache localisée
- [x] F3. Noms et descriptions des fournisseurs intégrés en anglais et malgache (cœur : champ i18n ; app : providerText)
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
- [x] (connexion Google testée par le propriétaire le 2026-10-12) Tester connexion, annulation, retour Android/Linux, déconnexion et reconnexion ; vérifier GitHub également.
- [ ] Relire le protocole de synchronisation séparément et vérifier la conservation des données.
- [ ] Réconcilier les anciennes cases non cochées (publication 0.2.0, F3 Apprendre) avec les preuves de livraison ; ne pas les considérer automatiquement comme fonctionnalités absentes.

- [x] (2026-10-12 : essai Google réel par le propriétaire réussi) Google reste en statut Testing sans utilisateurs de test : ajouter un testeur autorisé avant essai ; compléter présentation/confidentialité avant publication publique.
- [x] Tests ciblés PKCE et synchronisation : 5 tests réussis ; ne constitue pas un essai OAuth réel Android/Linux.

## v0.4.7 — retour Google/GitHub sur Android
- [x] Remplacer le serveur localhost Android par un lien natif vers Tontolo, sans nouvelle dépendance.
- [x] Conserver le PKCE temporaire dans le stockage sécurisé pour reprendre après redémarrage ; délai et suppression après usage.
- [x] Valider le lien reçu, ignorer les retours sans demande, empêcher les doubles échanges.
- [x] Ajouter le retour Android exact dans Supabase avec accord du propriétaire ; conserver le retour Linux et anciennes versions.
- [x] Tests : 192 cœur, 45 Flutter, analyse Flutter sans erreur ; dernier ajustement revérifié (analyse et 9 tests ciblés).
- [x] Trois APK signés construits ; installation par-dessus sur émulateur réussie (0.4.7, versionCode 4022), lien natif rouvre MainActivity à chaud et à froid.
- [x] Publication GitHub v0.4.7 (workflow 38162162769 réussi), fichiers présents et téléchargements en tête des notes ; SHA-256 de l’APK officiel x86_64 vérifié et installation par-dessus réussie.
- [x] Essai Google réel par le propriétaire : configuration Google en mode Testing à vérifier si accès refusé.


## v0.5.0 — isolation du contexte et continuité des médias (Codex)
- [x] R1. Dossiers : organiser sans injecter les réponses des autres fils.
- [x] R2. Mémoire : séparer capture explicite globale et capture automatique du fil ; préserver la provenance et sérialiser le compactage.
- [x] R3. Médias : référence dans le fil courant, sans réutiliser une ancienne image après un échec ; animation avec photo jointe et consignes de mouvement.
- [x] R4. Tests de frontières et de régénération, résumés et conservation des données.
- [x] R5. 203 tests cœur et 47 Flutter ; analyses/typage propres ; release v0.5.0 publiée (workflow 38166719297 réussi), APK officiel SHA-256 vérifié et installation sans effacement réussie.

- [ ] R6. Vérifier visuellement une vidéo réelle quand le quota LTX revient : l’essai réel du 2026-10-11 atteint le service mais reçoit « quota GPU gratuit épuisé ». Le code, l’image source exacte, le mode Gradio et les reprises sont testés avec fournisseurs simulés.

## v0.5.1 — demandes du 2026-10-11 (soir), après relecture du travail de Codex
Décisions du propriétaire : dossiers isolés par défaut avec partage activable par dossier ; mode Agent ET agents prêts à
l'emploi ; bureau Linux = fichiers + commandes confirmées dans un dossier choisi ; synchro = texte + créations ≤ 1 Mo + suivi en direct.
- [x] A0. Relecture Codex (0.4.7, 0.5.0) : tests verts, Supabase OK (retours Android/Linux, GitHub et Google actifs ; Google encore en « Testing ») ; incohérence : souvenirs automatiques extraits mais jamais rappelés → rappel limité à leur propre discussion
- [x] A1. Dossiers : interrupteur « Partager le contexte de ce dossier » (désactivé par défaut) ; priorité fil > dossier partagé > mémoire
- [x] A2. Modèles : liste plus claire, fiche détaillée (fournisseur, gratuit/payant, contexte, vision, outils, scores, vitesse, état), badge « Agent » pour les modèles agentiques
- [x] A3. Générateurs : liste simple des générateurs d'image, de vidéo et de son disponibles (état, quota)
- [x] A4. Mode Agent visible + agents prêts (Chercheur, Développeur, Rédacteur, Analyste) ; gratuit par défaut, payant possible, choix automatique sauf choix de l'utilisateur
- [x] A5. Compactage de la discussion automatique (désactivable) et manuel : fil structuré (sujets, faits, décisions, créations, tâches ouvertes) ; messages d'origine conservés
- [x] A6. Réponse coupée (limite de longueur) : relance « continue » automatique, 3 fois maximum, arrêt si rien de nouveau
- [x] A7. Bureau Linux : dossier de travail choisi, lecture/recherche/création/modification avec différences, sauvegarde et annulation, commandes du terminal confirmées une à une, dossiers sensibles bloqués
- [x] A8. Synchronisation : créations ≤ 1 Mo chiffrées, tâche en cours visible sur les autres appareils, synchro toutes les ~20 s quand l'application est ouverte
- [x] A9. Règle de version : x.y.9 → x.(y+1).0 ; x.9.9 → (x+1).0.0 ; script de montée de version + vérification CI
- [x] A11. Plusieurs fichiers demandés (ou nécessaires, ex. livre LaTeX en chapitres) : livrés ensemble dans une archive .zip (zipfile de Python, gratuit et local), avec la liste des fichiers
- [x] A12. Tâche complexe : découpage précis en étapes (plan visible) ; étapes indépendantes confiées à plusieurs modèles en simultané, ou livraison pas à pas avec un bouton « Continuer » ; le plan et l'avancement restent dans le fil
- [x] A13. Android en arrière-plan : la réponse continue quand on quitte l'application (service de premier plan) et, au retour, l'app se rattache au tour en cours au lieu d'annoncer « connexion coupée »
- [x] A14. Bug mobile : « convertis ce HTML en PDF » échoue sur Android → conversion HTML → PDF fiable sur mobile (sans dépendance de bureau)
- [x] A15. Navigateur web intégré (bureau Linux et tablette) que l'agent peut piloter (ouvrir, lire, cliquer, remplir avec confirmation) ; onglets bien gérés : réutiliser l'onglet de la tâche, jamais un onglet par commande ; moteur Chromium/Firefox (WebView) existant plutôt qu'un navigateur embarqué lourd
- [x] A16. Terminal intégré au bureau Linux : une session par discussion (pas un onglet par commande), commandes de l'agent visibles et confirmées, saisie libre de l'utilisateur
- [x] A16b. Vérification demandée : l'agent lit le terminal (terminal_read), y tape (terminal_send), voit la page (browser_look, testé avec un vrai modèle à vision), manipule le navigateur (testé avec Vivaldi réel) ; audit : discussion propre à chaque tour, secrets masqués, liens symboliques, dossiers cachés, boutons confirmés
- [x] A17. Tâches complexes : résultats intermédiaires (parties, étapes, sorties longues, brouillons) dans le dossier privé de l app, 7 jours après la fin, visibles et synchronisés (choix du propriétaire)
- [x] A10. Tests, émulateur, publication 0.5.1 — publiée (émulateur OK : mise à jour en place, onglet Agent, réponse continuée en arrière-plan puis rattachée ; tag v0.5.1 poussé)
- [x] A18. Espace disque : tous les caches de l'appareil dans UN dossier, sans doublons (fichiers temporaires de partage, profil du navigateur, médias synchronisés), avec plafonds et nettoyage
- [x] A19. Accueil d'une nouvelle discussion animé et vivant (comme Claude) : salutation selon l'heure et le prénom si connu (« Bonjour Antsa », « Bonsoir Antsa »), suggestions qui changent
- [x] A20. Pastilles d'activité : une discussion ou tâche en cours porte une pastille dans l'historique, distincte selon le lieu (sur CET appareil / sur un AUTRE appareil) ; si une discussion attend une réponse de l'utilisateur (question du modèle, confirmation d'outil, accord payant) pendant qu'il est ailleurs (autre discussion, Créations, Réglages, ou app en arrière-plan), Tontolo le signale (pastille « attend votre réponse » + notification)

## Consigne permanente (2026-10-12)
- À chaque mise à jour publiée : un poster de changelog simple mais complet, illustré, qui montre le changement majeur de la version par un exemple simple d'utilisation (voir docs/RELEASING.md)

## Audit de sécurité et de cohérence (2026-10-12, avant le poster)
- [x] Terminal : jeton obligatoire (sans jeton, aucun shell), processus fils récoltés (pas de zombie), commande refusée non recopiée
- [x] Navigateur : jamais l'API de Tontolo ni les métadonnées cloud ; boutons confirmés
- [x] Créations synchronisées : type de contenu validé, pages actives servies en téléchargement (CSP sandbox, nosniff)
- [x] LaTeX : lecture/exécution de fichiers refusées (\openin5, \read, \InputIfFileExists, \directlua… ; faille de frontière de mot corrigée)
- [x] Résultats de tâches : plafond global de 300 Mo ; planification plus sobre (plus de déclenchement sur la seule longueur)
- [x] Sélecteur de mode : seul le mode actif affiche son nom (icônes pour les autres)

## v0.5.3 (2026-10-12)
- [x] Bug « Tontolo demande toujours d'écrire un fichier » (livre de 200 pages) : cause = outil d'écriture de l'espace interne (fichier jamais livré, rien dans les résultats) → retiré sans dossier de travail ; les livres passent par un rédacteur dédié (plan, chapitres en parallèle, PDF/zip), résultats visibles en direct, demandes sans verbe reconnues, chapitre muet réessayé puis marqué « à refaire »
- [x] Poster 0.5.2 (fr, en, mg) ; système de poster par version (build_poster.py, exigé par la release, affiche embarquée dans « Nouveautés »)
- [x] Poster 0.5.3 (captures réelles de l'émulateur en fr/en/mg) ; publication 0.5.3 en cours ; posters à ajouter à la release 0.5.2
- [x] A20 pastilles d'activité (ici / autre appareil / attend votre réponse), badge du menu, avertissement + notification — prêt pour la version suivante

## Tests d'endurance, de longs projets et de complexité (2026-10-12, demandés par le propriétaire)
Règle : tout test, bug trouvé et optimisation est noté ici au fur et à mesure.
- [x] E1. (fait : core/bench/b1–b4 ; résultats dans docs/ENDURANCE.md) Bancs d'essai du cœur (fournisseurs simulés) : très longue discussion (milliers de messages, images, vidéos, fichiers), nombreuses discussions, tours en parallèle, arrêt/reprise, mémoire, synchro ; mesurer temps et mémoire
- [x] E2. Essais réels avec modèles gratuits : livre long, projet multi-fichiers, plan complexe en parallèle, chaîne de corrections, agent avec outils
- [ ] E3. Robustesse : entrées extrêmes (énormes, Unicode, injections), pannes de fournisseurs, coupures réseau, base verrouillée, disque plein
- [x] E4. Fuites et croissance : terminaux, onglets, résultats de tâches, caches, tâches de fond, connexions
- [ ] E5. Application : longue discussion à l'écran (défilement, mémoire), arrière-plan Android, synchro de gros volumes
- [ ] E6. Correctifs et optimisations issus de E1–E5 (liste ci-dessous, au fil de l'eau)

### Bugs trouvés et corrigés pendant les tests d'endurance
- [x] B1. Un fournisseur qui plante avec une exception inattendue (JSON, KeyError…) faisait échouer tout le tour au lieu de basculer sur un autre modèle → bascule sur toute exception
- [x] B2. Un fournisseur qui n'envoie que des signaux de maintien (ex. OpenRouter en file d'attente) bloquait le tour indéfiniment → premier mot sous 90 s, silence max 60 s, 200 s cumulées perdues au plus
- [x] B3. Créations longues (chapitres) : appel unique soumis au délai global de 120 s du fournisseur → diffusion
- [x] B4. Résumé de fil jeté si un message arrive pendant le résumé (starvation en usage rapide) → comparer le préfixe résumé au lieu de la révision entière
- [x] B5. Fil long jamais résumé (importé) : tout l'historique est envoyé au premier tour → fenêtre bornée sans résumé
- [x] B6. Résumé de fil : seuls les 24 000 derniers caractères étaient lus (début d'un gros fil importé perdu) → résumé « roulant » par blocs de 18 000 caractères (4 par passage)
- [x] B7. Fuite : les tours terminés (et tous leurs événements) s'accumulaient en mémoire tant que personne ne les relisait → nettoyage à chaque nouveau tour
- [x] B8. Texte avec demi-paire Unicode (« \ud800 ») dans un message ou une réponse de modèle : échec de l'enregistrement / du flux (réponse perdue) → assaini partout
- [x] B9. Entrées malformées → 500 : image_url sans url, catégorie inconnue (chat et catalogue), contenu invalide, message de plusieurs Mo → validation 4xx (message ≤ 1,5 M de caractères)
- [x] B10. (essai réel R4) Une correction de document échouait : le modèle ne commençait pas par « # Titre » après 3 reprises → Markdown rendu acceptable (introduction retirée, premier titre ou première ligne promu en titre), un titre seul reste refusé
- [x] B11. (essai réel R4) Après une correction échouée, « excellent mais plus court » partait en discussion (dernier fichier introuvable) → on repart du dernier fichier livré
- [x] B12. (essai réel R4) En discussion normale, le modèle recevait les outils terminal/navigateur/écriture et tentait de créer un fichier Word par le terminal → ces outils sont réservés au mode Agent (économie d'environ 1,5 k jetons par demande)
- [x] B13. (E5) Une discussion de milliers de messages était chargée en une seule requête par l’app → chargement par fenêtre (120 derniers, `?tail=&before=`), bouton « Messages précédents (n) » en tête, test Flutter
- [x] B14. (essai réel R7, livre de 21 pages) Erreur LaTeX « clé inconnue /tcb/… » : la ligne fautive était perdue du journal, le chapitre n’était pas retrouvé et le livre échouait → ligne `l.N` conservée, recherche du texte fautif dans les chapitres, et dernier recours `plain_chapter` (chapitre simplifié) au lieu d’abandonner le livre
- [x] R7 livre de 21 pages : PDF de 18 pages en 932 s après B14
- [x] O1. (essai réel R3 : 47 s par tour, réponses de 2 à 6 k caractères d’un modèle 550B lent) Vitesse réellement observée par modèle (car./s, attente comprise, moyenne glissante) mêlée à celle du catalogue (souvent absente pour les gratuits) : le routeur favorise les modèles rapides, surtout en « réponse rapide d’bord »
- [x] R3 longue discussion (14 tours, prénom et ville retrouvés) et R4 chaîne de 4 corrections (aucun nom de fichier dupliqué) OK
- [x] E2 (partiel) : R2 plan complexe, R6 projet de code, R8 outils agent OK ; R4 chaîne de corrections, R3 longue discussion, R7 livre à relancer sur le code corrigé

## Questions interactives à choix (demande de l'utilisateur, 2026-10-12)
- [x] Outil `ask_user` (1 à 4 questions, 2 à 6 options, choix multiple possible) : le tour s'arrête sur un événement `question` ; la réponse revient comme un message normal
- [x] Consigne système : poser les questions d'abord pour les demandes ouvertes ou complexes (projet, document, plan, code, recherche), jamais pour une demande claire ; jamais deux séries d'affilée ; pas en mode Apprendre (le tuteur interroge déjà)
- [x] App : carte de puces (fr/en/mg), un toucher envoie si une seule question à choix unique, sinon « Envoyer mes choix » ; la carte revient à la réouverture si la question est la dernière ; pastille « attend une réponse »
- [x] Demandes de création de fichier (circuit créateur) : public et longueur demandés d'abord quand ils manquent (questions fixes fr/en/mg, sans appel de modèle ; jamais pour une conversion « convertis ce HTML en PDF » ni une demande déjà détaillée) ; la réponse relance la création avec la demande complétée
- [x] Optimisation : `_last_file` et le contexte de création lisent une fenêtre de 12 messages au lieu du fil entier
- [x] Essai émulateur : carte affichée, choix envoyés, création relancée avec la demande complétée
- [x] Bug trouvé à l'essai : questions dans la langue de l'interface (malgache) pour une demande en français → langue détectée sur la demande
- [x] Bug trouvé à l'essai (malgache) : « Manorata tatitra Word… » non reconnu comme création (verbes malgaches manorata, amboary, vokary, avoahy ; « amin'ny pdf ») ; consigne : ne jamais écrire les questions en texte quand ask_user est disponible
- [x] Champ libre « Autre précision (facultatif)… » dans la carte (ajouté à la réponse) — après 0.5.6
- [x] Essai réel R9 : 4 demandes ouvertes sur 4 donnent une carte (ling-3.1-flash, DeepSeek-V4-Flash, Qwen3.8-27B, nemotron-3-ultra), dans la langue de la demande ; aucune carte pour une question simple
- [x] B15. (essai réel R3) Questions posées au 3e tour alors que le contexte suffisait → en pleine discussion, `ask_user` seulement pour une nouvelle demande d'au moins 15 mots
- [x] B16. (essai réel R3) Tour sans réponse plus de 10 min : un modèle qui « réfléchit » sans fin n'était jamais vu comme silencieux → limite de réflexion sans texte de réponse (150 s, 300 s pour les créations), puis bascule ; réglages du routeur jamais envoyés au fournisseur


## Fournisseurs, mémoire sémantique, mode avancé (demande du 2026-10-12)
Philosophie gardée : gratuit d'abord, clés de l'utilisateur, rien ne passe par un intermédiaire, une clé n'est envoyée qu'à l'hôte prévu (HTTPS, épinglé).
- [x] F1. Registre intégré de fournisseurs (gratuits et payants directs) en plus de la liste en ligne : gratuits à clé (Cerebras, SambaNova, GitHub Models, Together « -Free »…), payants directs avec prix connu (Mistral, Google, Moonshot, Qwen, Z.ai, Cohere, Perplexity, MiniMax…) ; modèles découverts par `GET /models` quand la clé est là ; adresse codée en dur (jamais remplaçable par une source en ligne)
- [x] F2. App : les nouveaux fournisseurs apparaissent dans la liste des clés avec lien « obtenir une clé », gratuit/payant indiqué
- [x] F3. Noms et descriptions des fournisseurs intégrés en anglais et malgache (cœur : champ i18n ; app : providerText)
- [x] M1. Mémoire sémantique unifiée : un même index local (vecteurs de trigrammes, sans dépendance, toutes langues) pour les souvenirs ET les réponses déjà données
- [x] M2. Cache sémantique : question quasi identique, sans dépendance au temps ni au contexte → réponse réutilisée immédiatement (« déjà répondu le … », Régénérer contourne) ; question proche → réponse antérieure fournie en contexte ; jamais pour l'actualité, les fichiers, les photos, le mode Apprendre ; effacé avec la discussion ; réglage « Réutiliser les réponses » + Vider
- [x] A1. Mode avancé : fournisseurs personnalisés compatibles OpenAI (HTTPS obligatoire, hôte épinglé, test de connexion, clé dans le stockage sécurisé)
- [x] A2. Mode avancé : enchaînements de modèles définis par l'utilisateur (par catégorie), fournisseurs exclus/préférés
- [x] A3. Mode avancé : délais du routeur réglables dans des bornes sûres ; export/import des réglages avancés sans les clés

## Notations et QR code (demande du 2026-10-12, pour 0.5.8)
Principe : rien de ce qui est écrit ne quitte l'appareil ; seule la note (modèle, type de demande, 👍/👎, raison) est partagée, avec l'accord « Statistiques anonymes ».
- [x] N1. Cœur : `POST /tontolo/feedback` (note d'une réponse, modifiable) ; table locale ; le modèle et le type de demande sont retrouvés à partir du message
- [x] N2. Récompense / pénalité locale : bonus borné dans le classement du modèle pour ce type de demande (👍 +, 👎 −), visible dans « Pourquoi ce modèle »
- [x] N3. 👎 : la réponse sort du cache des réponses ; proposition « Réessayer avec un autre modèle » (ce modèle évité pour ce tour) ; raisons rapides (inexact, hors sujet, trop long, langue, autre)
- [x] N4. Supabase : table `ratings` (insertion seule, une note par appareil et par réponse) + fonction `model_scores()` agrégée (appareils distincts, seuil minimal) lisible par l'app ; script SQL et docs/STATS.md
- [x] N5. App : 👍/👎 sous chaque réponse ; envoi groupé avec les statistiques quotidiennes (file d'attente locale, rien sans accord) ; « Voir ce qui est envoyé » montre les notes
- [x] N6. Retour global : l'app récupère `model_scores()` une fois par jour et le transmet au cœur → bonus/malus collectif borné (plus faible que le local)
- [ ] N7. Le propriétaire exécute docs/stats/supabase_ratings.sql dans Supabase (0.5.8 publiée sans : les notes agissent sur chaque appareil et attendent en file, 500 au plus, jusqu'à la création de la table)
- [x] Essai émulateur : 👍/👎 visibles, panneau des raisons (malgache), « autre modèle » (ling-3.1-flash → Qwen3.6), note enregistrée ; QR « À propos » lu depuis l'écran (zbarimg)
- [x] Q1. QR code vers le téléchargement : généré par script (`qrencode`), vérifié par lecture (`zbarimg`) ; dans « À propos » (dernière version) et sur le poster de chaque version (page de cette version)
- [x] R. Version 0.5.8 : CHANGELOG, nouveautés fr/en/mg, poster (avec QR), tests, essais émulateur

## Pièces jointes de tous types (demande du 2026-10-12)
Outils gratuits, locaux d'abord ; rien n'est exécuté depuis une pièce jointe.
- [x] P1. Inventaire : ce que l'app accepte aujourd'hui (images, PDF…) et comment le cœur l'extrait (documents.py)
- [x] P2. Texte et code : md, txt, csv, json, html, xml, yaml, sources (py, js, dart…) → lus tels quels (taille bornée)
- [x] P3. Documents : docx, pptx, xlsx, odt/ods/odp, epub, rtf → texte extrait (bibliothèques pures Python déjà utilisées ou stdlib zip/xml)
- [x] P4. Archives zip (et tar.gz) : liste + extraction en mémoire des fichiers lisibles, avec garde-fous (bombe zip, chemins « ../ », taille et nombre de fichiers bornés)
- [x] P5. Son : transcription (modèle STT gratuit déjà routé : catégorie stt) ; vidéo : piste son transcrite + quelques images clés (ffmpeg s'il est présent sur le bureau ; Android : son seulement si possible)
- [x] Essai émulateur : zip choisi dans le sélecteur (tous types), lu (3 pages), contenu juste dans la réponse
- [x] B17. (essai émulateur) Le relecteur (équipe de modèles) ne voyait pas les documents joints et accusait la réponse d'inventer leur contenu → il reçoit documents et fin du fil
- [x] B18. (essai émulateur) Carte de questions pour « résume ce fichier » → jamais pour une demande de résumé
- [ ] P7. Vidéo : quelques images clés (ffmpeg) analysées par un modèle de vision, en plus de la transcription
- [x] P6. App : sélecteur de fichiers élargi, aperçu par type (icône, nom, taille), limites claires ; tests de chaque type et des fichiers piégés

## Orchestration multi-modèles et durcissement (demande du 2026-10-12)
Contraintes : rien ne change par défaut (`orchestrate=false`), léger (asyncio, httpx, re), modèles gratuits seulement, sécurité d'abord.
- [x] S1. Audit secrets.py / server/app.py / WebSockets / MCP ; bandit
- [x] S2. secrets.json chiffré en repli (Fernet si `cryptography` présent, sinon chiffrement léger stdlib), migration transparente des fichiers existants
- [x] S3. Limitation de débit des WebSockets (connexions et messages)
- [x] S4. MCP durci : commandes dangereuses refusées, taille des requêtes bornée, configuration stdio réservée à l'appareil
- [x] O1. Paquet `orchestrator/` : TaskDecomposer (regex, repli Ollama local), ResponseSynthesizer (low/medium/high), HierarchicalPipeline (cache, gather, délais, replis, routeur existant)
- [x] O2. `/tontolo/chat` : `orchestrate: bool = false` ; complexité faible → flux normal ; métriques (durée, modèles) dans les événements
- [x] O3. tests/test_orchestrator.py + essai « code Python + explication »
- [x] Essai réel R10 : « code + explication » (dépendance respectée, 64 s, 2 modèles) ; 3 parties en parallèle 19 s au lieu de 23 s en série, réponses justes ; « Bonjour » non orchestré
- [ ] O4. Fusion « medium » : le petit modèle des résumés renvoie souvent une fusion trop courte → repli sur la concaténation (sûr) ; essayer un modèle d'écriture rapide
- [ ] O5. App : interrupteur « Orchestration » en mode avancé (l'API est prête, rien n'est activé par défaut)
