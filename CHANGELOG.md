# Journal des modifications

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement
[SemVer](https://semver.org/lang/fr/).

## [Non publié]

## [0.4.2] - 2026-10-11

### Corrigé
- Équipe de modèles : quand le relecteur prévu était indisponible, la bascule automatique
  pouvait renvoyer la relecture au rédacteur lui-même, affichée « relu par » le même modèle.
  Une auto-relecture n'est plus comptée ni affichée comme une vérification croisée.
- Tailles de fichiers dans la langue de l'interface (KB / Ko) ; « Your level: » sans espace
  avant les deux-points en anglais.

## [0.4.1] - 2026-10-11

### Corrigé
- Réponses dans la langue du dernier message : une demande en anglais (ou en malgache)
  recevait parfois une réponse en français, notamment les quiz du mode Apprendre (consignes du
  modèle rédigées en français). Règle de langue explicite en tête des consignes.

## [0.4.0] - 2026-10-11

### Ajouté
- **Créer tout type de fichier** à la demande (« génère un document Word… », « fais une carte
  mentale… », « exporte en PDF », raccourci « Créer un fichier ») : DOCX, PDF (LaTeX compilé),
  source LaTeX, Excel (XLSX, formules), PowerPoint (PPTX), cartes mentales et schémas en images
  nettes, graphiques, et tout fichier texte (CSV, JSON, HTML, SVG, Markdown, code, calendrier…).
- **Équipe de modèles** : un modèle rédige, le fichier est réellement construit et vérifié
  (compilation, structure, mise en page), les erreurs lui sont renvoyées pour correction (jusqu'à
  3 fois), puis un modèle **d'une autre famille** relit (en voyant l'image ou les pages quand
  c'est possible) avant livraison. Un fichier qui ne se construit pas n'est jamais livré.
- Réponses de **maths, code et raisonnement vérifiées par un second modèle** : « Vérifié par… »
  ou les erreurs relevées avec un bouton « Corriger » (réglage « Équipe de modèles »).
- Carte « fichier » dans la discussion : ouvrir, partager, enregistrer ; étapes en direct.
- Services de création gratuits et sans compte, avec repli automatique (LaTeX-on-HTTP,
  latexonline.cc, Kroki, QuickChart) ; moteurs locaux utilisés s'ils sont installés. Les modèles
  payants autorisés dans Réglages (OpenAI, Anthropic, DeepSeek, xAI, OpenRouter) rejoignent
  automatiquement l'équipe, dans la limite du plafond.

### Modifié
- **Mode Apprendre plus simple et plus strict** : accueil réduit à une question, le niveau en un
  geste et quatre grandes actions (« Mon exercice », « Comprendre une leçon », « Me tester »,
  « Carte mentale »), le reste dans « Plus » ; le tuteur ne donne jamais la réponse finale, même
  sur demande : « Montre la solution » devient « Étape suivante ».

## [0.3.0] - 2026-10-11

### Ajouté
- **Mode Apprendre** (élèves et étudiants) : bascule Général / Apprendre bien visible en haut,
  niveau scolaire et matière, tuteur qui guide pas à pas sans donner la réponse (indices
  progressifs, correction ciblée, solution seulement sur demande), **quiz interactifs** et
  **fiches de révision** à retourner, plan de révision, actions rapides (« Un indice », « Je ne
  comprends pas », « Montre la solution »…). Le mode est mémorisé par discussion.
- **Importer une discussion** de Claude, ChatGPT ou Gemini (lien de partage collé dans le chat
  ou « Importer une discussion » dans le volet), d'un texte collé ou d'un fichier d'export,
  pour la continuer dans Tontolo. Lien Claude privé : explication pour créer un lien de partage.
- **Comptes Google / GitHub et synchronisation chiffrée de bout en bout** (facultatifs) :
  discussions, mémoires et clés d'API sur tous les appareils ; phrase secrète jamais transmise,
  AES-256-GCM (voir docs/ACCOUNTS.md).
- **Aide pas à pas pour chaque clé d'API** (où cliquer, à quoi ressemble la clé, coût).
- **Modèles payants en version simple** dans les Réglages : OpenRouter, OpenAI, Anthropic,
  DeepSeek, xAI ; utilisés en secours, plafond mensuel en un geste, dépense du mois affichée.
- **Images** : FLUX.1 schnell/dev et Stable Diffusion 3.5 Turbo (Spaces Hugging Face gratuits)
  avant Pollinations, avec repli automatique.
- Guide de publication (Play Store, F-Droid/IzzyOnDroid, AUR, Flathub, Snap, PyPI) et fichiers
  d'empaquetage (`packaging/`, `fastlane/`).

### Modifié
- Choix du modèle réévalué à chaque message selon le **sujet de la discussion** : une relance
  courte (« et pourquoi ? ») garde un modèle adapté au code ou aux maths.
- Quota GPU gratuit de Hugging Face épuisé : tous les Spaces sont mis en pause d'un coup.

### Sécurité
- Les fournisseurs intégrés ne peuvent plus être redéfinis par une liste distante (la clé
  n'est envoyée qu'à l'adresse codée en dur).
- Import : JSON imbriqué à l'excès refusé proprement ; seules des adresses construites à
  partir d'un identifiant validé sont téléchargées ; vue web limitée aux pages https.

## [0.2.11] - 2026-10-11

### Ajouté
- **Documents** : PDF, texte, Markdown ou HTML joints par le bouton + ; texte extrait sur
  l'appareil, extraits pertinents fournis au modèle, réponses avec citations « [nom, p. N] ».
- **Dossiers de discussions** (filtres dans le volet, « Déplacer vers un dossier ») et
  **recherche plein texte** avec extrait du passage trouvé.
- **Partager en page web** : discussion exportée en un fichier HTML autonome et sûr (aucun
  script possible, liens limités à http/https).
- **Modèles sur l'appareil** : Ollama et llama.cpp détectés sur 127.0.0.1, utilisés en dernier
  recours et immédiatement hors ligne.
- Page de release réorganisée : fichiers à télécharger en premier, puis nouveautés et détails.

## [0.2.10] - 2026-10-11

### Corrigé
- « Draw a woman wearing gucci. » répondu par un modèle de texte qui prétendait avoir créé
  l'image : la **modification d'un message** ne détectait pas les demandes d'image, de vidéo
  ou de voix (elle est maintenant traitée comme un média). Filet de sécurité : si un modèle de
  texte prétend avoir généré une image (« I've generated an image… », « voici l'image »), Tontolo
  bascule vers une vraie création.
- Raisons de bascule traduites (« problème réseau » s'affichait en français dans l'interface
  anglaise ou malagasy).
- Malagasy : termes validés par l'auteur (Kirakira, Fanalahidy, Mandeha ho azy, Fintinina…).

### Ajouté
- **Crédits de l'auteur** — RANIRIAMANJAKA Antsa · github.com/raantss18 ·
  antsa.raniriamanjaka@univ-antananarivo.mg · +261 33 43 838 82 — dans « À propos » (liens
  GitHub, e-mail, téléphone, WhatsApp), dans chaque annonce de mise à jour et « Quoi de neuf »,
  le README, le NOTICE, les notes de release et les métadonnées du paquet Python.
- **Statistiques anonymes d'utilisation** (Supabase) : une fois par jour au plus, identifiant
  aléatoire d'installation, version, système, langue, pays de la langue du téléphone, nombre de
  messages — jamais le contenu. Annoncées dans l'accueil, désactivables, données visibles
  (« Voir ce qui est envoyé »). Inactives tant que la base n'est pas configurée
  (`docs/STATS.md`, `docs/stats/supabase.sql`).

### Sécurité (audit du 2026-10-11, voir SECURITY.md)
- Flux XML distant : DTD et entités refusées.
- Vidéo : téléchargement sans redirection (la clé Hugging Face reste sur le domaine du Space)
  et plafonné pendant le transfert.
- Retouche locale : dimensions vérifiées avant décodage (images piégées).
- Le dossier de travail de l'agent n'est plus modifiable par l'API.
- `bandit` et `pip-audit` : aucune vulnérabilité restante connue.

## [0.2.9] - 2026-10-11

### Corrigé
- « Manaova sary tilikambo jiro » (et toute création d'image dont les sources étaient en pause
  après une panne) répondait « Aucune source gratuite disponible pour ce type de média ». Les
  sources en pause sont maintenant retentées pour un média demandé explicitement.
- Les demandes d'image et de vidéo en français ou en malagasy sont reformulées en anglais par le
  meilleur modèle de traduction avant la création (« tilikambo jiro » → un phare, et non une
  ampoule).

### Ajouté
- **Bouton « Régénérer »** sous toute création en échec, et « Réessayer » sur les erreurs du chat.
- **Notification « de nouveau disponible »** : après un quota épuisé ou une pause, l'heure de
  retour est affichée et une notification est programmée (Android : par le système, même
  application fermée ; Linux : tant que l'application est ouverte). Annulée si une nouvelle
  tentative réussit avant.
- **File d'attente hors ligne** : sans réseau, le message attend et part tout seul au retour de
  la connexion (vérification toutes les 8 s et au retour au premier plan), annulable.
- **Page « État des modèles »** : prêts, en pause (avec raison et heure de retour), épuisés pour
  la journée ; accessible depuis le sélecteur de modèle et les réglages.
- **Option « Réponse rapide d'abord »** : le modèle le plus rapide pour les demandes simples, le
  meilleur pour le raisonnement, le code et les maths.
- API : `GET /tontolo/online`, codes d'erreur stables (`code`, `params.error_code`,
  `params.retry_at`, `params.warning_code`) pour traduire les messages dans l'application.

### Langues
- **Malagasy complet** (180 textes ajoutés) et anglais complet : plus aucune chaîne française
  dans l'interface en anglais ou en malagasy (filtres, galerie, réglages avancés, « Pourquoi ce
  modèle ? », À propos, étapes de retouche, mises à jour, notifications, erreurs du moteur).
  Un test vérifie qu'aucune traduction ne manque et que les variables sont conservées.
- Le moteur répond par défaut dans la langue de l'interface ; le classifieur comprend les
  demandes malagasy (image, vidéo, « ampihetsiho ity sary ity », retouche, recherche, traduction).

## [0.2.8] - 2026-10-11

### Ajouté
- **Écran d'accueil interactif** : 8 raccourcis colorés (créer une image, une vidéo, retoucher
  ou animer une photo, chercher sur le web, traduire, expliquer, résumer) qui préparent la
  demande sans l'envoyer (la photo est demandée si besoin), et 3 exemples qui changent chaque
  jour. Grille adaptée au téléphone, à la tablette et au bureau.
- **Pastille de santé** sur le bouton du modèle : verte, orange ou rouge selon le nombre de
  modèles gratuits prêts (rouge aussi hors ligne), avec le détail au survol et en tête du
  sélecteur. Mise à jour au démarrage, après chaque réponse et toutes les 45 s.
- **Appui long** sur le bouton du modèle : les 5 meilleurs modèles gratuits prêts, à fixer pour
  la discussion d'un geste (ou retour en Auto).
- Sélecteur de modèle : point d'état par modèle (prêt / en pause).
- API : `GET /tontolo/health` (état global) et `available_at` dans `/tontolo/catalog`.

## [0.2.7] - 2026-10-11

### Ajouté
- **Vidéo gratuite, sans clé** : texte → vidéo et photo → vidéo (« anime cette photo ») par le
  Space officiel LTX-Video de Lightricks sur Hugging Face (GPU partagé). Vidéo de 1 à 8 s
  (4 s par défaut), cadrage portrait respecté pour une photo, lecture intégrée sous Android et
  par le lecteur du système sous Linux. Le quota GPU anonyme est de quelques vidéos par jour :
  une clé Hugging Face gratuite (Réglages) l'augmente, et un message clair l'explique quand il
  est atteint.
- Détection des demandes de vidéo plus précise : « crée / fais / génère une vidéo… », « une
  vidéo de… », « anime cette photo » ; une simple mention (« explique cette vidéo ») reste une
  question.

### Corrigé
- Mises à jour : quand l'API GitHub refusait la requête (limite de 60 requêtes/heure par
  adresse IP, fréquente sur réseau mobile), la recherche échouait sans rien dire. Repli sur la
  page `releases/latest` (sans limite) ; « Rechercher des mises à jour » affiche toujours le
  résultat et rouvre l'annonce si une version est prête.
- Saut de versions (par exemple 0.2.0 → dernière) : l'annonce présente les changements de
  **toutes** les versions sautées, et « Quoi de neuf » toutes les nouveautés intermédiaires.

### Sécurité et compatibilité
- La CI refuse de publier une release qui casserait la mise à jour des versions installées
  depuis la 0.2.0 (noms de fichiers, empreintes, CHANGELOG, numéro de build croissant) ; test
  d'ouverture d'une base de données créée par la 0.2.0.

## [0.2.6] - 2026-10-11

### Modifié
- Téléphone : la barre de navigation du bas est supprimée ; Créations et Réglages sont dans le
  volet des discussions, sous « Nouvelle conversation ». Ces écrans ont une flèche de retour et
  le bouton retour d'Android ramène à la discussion au lieu de quitter. La barre latérale du
  bureau et de la tablette ne change pas.

### Documentation
- Alerte « Google Play Protect : analyse recommandée » expliquée (README, notes de release) et
  démarches pour la faire disparaître (`docs/RELEASING.md`).

## [0.2.5] - 2026-10-10

### Corrigé
- Sans connexion Internet (ou avec un réseau mobile qui saute), l'application essayait les
  modèles un par un en affichant « problème réseau » pour chacun, pénalisait des modèles sains
  puis échouait avec « Tous les modèles gratuits ont échoué ». Sur une erreur réseau, le cœur
  teste maintenant la connexion : si l'appareil est hors ligne, il attend jusqu'à 25 s le retour
  du réseau, reprend avec le **même** modèle (sans bascule, sans pénalité de quota ni de fiabilité)
  et, sinon, affiche « Pas de connexion Internet » une seule fois.
- Les connexions persistantes mortes sont abandonnées au retour du réseau.
- Une série de bascules consécutives s'affiche sur une seule ligne avec le total.

## [0.2.4] - 2026-10-10

### Corrigé
- Formules dans un tableau : le rendu échouait quand le style de texte de la cellule n'avait
  ni taille ni couleur. Un « $ » oublié par le modèle (« en $a**. Géométriquement, $f(a)$ »)
  reliait deux formules à travers la phrase : une « formule » contenant du gras ou une fin
  de phrase est maintenant gardée comme texte.
- Le bloc « Réflexion du modèle » ne pouvait pas afficher son effet au toucher (bulle sans
  surface Material).
- Un lecteur audio était créé pour chaque carte d'image : il n'est plus créé que pour un son
  (mémoire et démarrage allégés).
- Création d'image : 2 essais de 45 s au plus (au lieu de 3 × 120 s) quand le service gratuit
  ne répond plus ; l'attente maximale passe d'environ 6 minutes à 90 secondes.

### Ajouté
- Captures d'écran dans le README et banc de démonstration (`docs/DEMO.md`).

## [0.2.3] - 2026-10-10

### Corrigé
- **Retouche de photo qui ne suivait pas la consigne** : « édite cette photo de façon
  professionnelle sans changer la personne ni la composition » générait une autre personne.
  Les retouches (lumière, contraste, couleurs, netteté, noir et blanc, sépia, vintage,
  dramatique, HDR, tons chauds/froids, style professionnel, amélioration automatique) sont
  maintenant appliquées **sur l'appareil, directement sur la photo** : personne et
  composition intactes, rien n'est envoyé en ligne. Si la consigne demande de changer le
  contenu (décor, objets, style artistique) tout en interdisant de changer la personne,
  l'application l'indique honnêtement au lieu de recréer une image qui désobéit.
- Avec une photo jointe, les verbes de retouche (remplace, transforme, améliore…) sont
  reconnus comme une édition et non comme une simple question.
- « crée la photo » (avec un article) n'était pas reconnu comme une demande d'image et partait
  vers un modèle de texte. Détection élargie : verbes (crée, fais, montre, imagine,
  refais…), articles quelconques, formes en anglais, et demandes de suite (« vas-y »,
  « refais », « encore ») qui reprennent la demande d'image précédente.
- Les réponses « image » de l'historique étaient présentées aux modèles de texte sous la
  forme brute `[média:…]` : ils les prenaient pour de faux espaces réservés et
  prétendaient ne pas savoir générer d'images. Elles sont maintenant expliquées en clair.

### Ajouté
- **Bascule automatique vers l'image** : si un modèle de texte répond qu'il ne peut pas
  générer d'image alors que l'utilisateur en demandait une, la réponse de refus est écartée
  et la génération d'image est lancée, sans intervention.

## [0.2.2] - 2026-10-10

### Corrigé
- « Édite cette photo » répondait « Aucune source gratuite disponible » : aucun service
  gratuit ne retouche réellement une photo. Un modèle gratuit à vision décrit désormais la
  photo, puis une image est recréée avec la transformation demandée ; un avertissement
  explique qu'il s'agit d'une réinterprétation (ou d'une création à partir du texte seul si
  aucune IA gratuite ne peut lire la photo).
- Les photos jointes sont réduites (1024 px) avant l'envoi : elles étaient trop lourdes pour
  les IA gratuites et alourdissaient la base locale.

## [0.2.1] - 2026-10-10

### Corrigé
- **L'application s'arrêtait quand on la quittait puis la rouvrait** : Android garde le
  processus (et le moteur Python) mais recrée l'interface, qui tentait d'en démarrer un
  second. Le moteur déjà en marche est maintenant retrouvé et réutilisé.
- Quitter une discussion pendant qu'un modèle répond n'interrompt plus la réponse : elle
  continue côté moteur, est enregistrée, et on s'y rattache en revenant (rejeu puis direct).
  Le moteur embarqué est aussi protégé contre les arrêts inattendus.
- Impossible de remonter le fil pendant que le modèle écrit ou réfléchit : le suivi
  automatique du bas est suspendu tant que le doigt est posé ou que le fil défile, et ne
  reprend que si l'on s'arrête en bas ; un bouton ramène au dernier message.
- Message d'erreur d'image affiché en double ; « Réessayer » relançait du texte au lieu de
  l'image. Pollinations : 3 essais automatiques et variante « auto » plus fiable.
- Bouton Arrêter : interrompt réellement la génération côté moteur.

### Ajouté
- Les notes de release indiquent quel fichier choisir (ARMv8/arm64-v8a, armv7, x86_64,
  AppImage) et les versions d'Android compatibles.
- La réflexion des modèles à raisonnement est affichée en direct (repliable) au lieu
  d'un écran vide pendant de longues minutes.
- **Mises à jour visibles** : annonce avec le résumé des changements dès qu'une version est
  prête (installer maintenant ou plus tard), bannière dans le chat, entrées dans
  Réglages › Simple ; l'installation n'est plus lancée sans demander.
- **Nouveautés** présentées au premier lancement après une mise à jour, et consultables
  dans Réglages › Simple › Nouveautés de cette version.

## [0.2.0] - 2026-10-10

### Ajouté
- **Mémoire à long terme locale** avec compactage automatique : « souviens-toi que… »,
  extraction automatique des préférences, rappel des souvenirs pertinents, fusion des
  doublons et regroupement par un petit modèle gratuit ; secrets jamais mémorisés.
- **Instructions personnalisées** (Réglages › Personnalisation).
- **Régénérer** la dernière réponse, **modifier et renvoyer** un message.
- **Épingler** des conversations, **exporter** une conversation en Markdown, partager un message.
- **Raccourcis « / »** : modèles de demandes (résumé, explication, traduction, correction,
  code, quiz, e-mail).
- **Plus de 30 modèles gratuits sans clé** : Kilo Code, LLM7 et OVHcloud détectés depuis la
  source en ligne, en plus de Pollinations ; la bascule fonctionne même sans aucune clé.
- Attente courte automatique (≤ 30 s) quand tous les modèles sont momentanément occupés.
- Vitesse de lecture à voix haute réglable.

### Corrigé
- La lecture à voix haute ne pouvait pas être arrêtée : bouton lecture/arrêt, une seule
  lecture à la fois, voix par défaut si la voix de la langue n'est pas installée.
- « Réessayer » dupliquait le message ; bandeau « relancée sur un autre modèle » trompeur.
- Heure de retour estimée affichée dans le passé.
- CLI : au premier lancement, `catalog list` attend le chargement des classements.

### Sécurité
- Protection CSRF (en-tête Origin) et DNS rebinding (en-tête Host) du serveur local.
- `fetch_url` protégé contre la SSRF (adresses privées et locales, redirections revérifiées,
  taille maximale).
- Clés envoyées uniquement en HTTPS à un hôte de fournisseur épinglé à la première
  utilisation (protection contre une source en ligne compromise).
- Calculatrice : longueur et durée maximales ; masquage élargi des clés dans les journaux.
- Serveurs MCP `stdio` non configurables à distance ; envois de fichiers limités à 25 Mo.
- Liens ouverts uniquement en http(s)/mailto ; mises à jour téléchargées uniquement depuis GitHub.

### Compatibilité
- Testé sur Android 10 (API 29) et Android 16 (API 36) ; minimum Android 7 (API 24).

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
