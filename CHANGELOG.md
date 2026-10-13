# Journal des modifications

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement
[SemVer](https://semver.org/lang/fr/).

## [Non publié]

### Corrigé
- Export PDF : tableaux Markdown lisibles (plus de lignes |---|), liens `<…>` nettoyés, trait
  d'union insécable (« ci‑dessus » s'affichait « ci?dessus »).
- Synchronisation : deux appareils qui continuaient la même discussion hors ligne perdaient les
  messages de l'appareil le moins récent. Ils sont désormais gardés dans une copie « (autre
  appareil) ». Une suppression reste une suppression ; une réponse régénérée remplace l'ancienne.
- Disque plein ou mémoire de Tontolo occupée : message clair (fr/en/mg) au lieu de « Erreur
  interne », et reprise sans redémarrage.

### Modifié
- Nouveau logo : l'Afrique et Madagascar (en orange), un anneau ouvert aux extrémités effilées
  et un « T » fin à boucle posé sur le continent ; l'Afrique s'estompe vers le nord et le cercle
  se poursuit en pointillés, comme un logo encore en train d'être tracé. Icône Android
  adaptative et monochrome, icône Linux et pages de présentation mises à jour.

## [0.6.2] - 2026-10-13

### Sécurité
- Mises à jour Linux signées : les empreintes de chaque version (`SHA256SUMS`) sont signées en
  Ed25519 par la CI ; l'application refuse une mise à jour dont la signature est absente ou
  invalide, avant même de vérifier l'empreinte du fichier.

### Ajouté
- Suivi d'une réponse en cours : une ligne « modèle · ce qu'il fait · pourcentage » avec une
  barre d'avancement estimée (étapes, texte reçu, temps écoulé ; jamais en recul). Un toucher
  ouvre « Ce que fait Tontolo » : le journal horodaté (modèle choisi, bascules, outils,
  parties confiées à plusieurs modèles, relecture).
- La réflexion du modèle n'est plus un texte brut qui défile : une ligne courte, le détail
  complet à un toucher.

### Corrigé
- Formules dans une phrase : le texte qui suit n’est plus rejeté à la ligne suivante
  (« … en gras a²+b²=c², puis … » reste sur la même ligne) ; une formule `$$…$$` seule sur
  sa ligne reste centrée.

## [0.6.1] - 2026-10-13

### Ajouté
- Vidéos jointes : en plus de la transcription du son, quatre images clés (extraites sur
  l’appareil : lecteur vidéo du système sous Android, ffmpeg sous Linux) sont décrites par un
  modèle à vision : diapositives, tableau, formules, schémas à l’écran. Une vidéo muette, ou
  trop lourde pour être transcrite, est désormais comprise.
- Export PDF d’une discussion (menu ⋮ › « Exporter en PDF »), produit sur l’appareil, sans
  dépendance ni service en ligne : la discussion reste privée.
- Premier lancement hors ligne : un catalogue de secours embarqué (40 modèles gratuits sans
  clé) évite un écran sans modèle ; il est remplacé dès le premier téléchargement.
- Métriques locales `/tontolo/metrics` (format Prometheus : tours, appels par modèle, durées,
  erreurs, cache) ; rien n’est envoyé.
- Documentation de l’API (`docs/API.md`, générée et vérifiée par un test).

### Modifié
- Serveur découpé en dix routeurs thématiques ; API strictement identique (schéma OpenAPI
  vérifié à l’octet près).
- Garde-fou de performance en CI (30 utilisateurs simultanés, fil de 1 500 messages).
- Tests Flutter des écrans : réglages, questions à choix, notes, fiches.

### Corrigé
- Une question sur une vidéo ou une musique existante lançait une génération (« que montre
  la vidéo ? », « inona no asehon’ity horonan-tsary ity ? », « que raconte cette musique ? »,
  « hazavao ny hira ») : un verbe de création est désormais requis, et « la / cette / ma
  vidéo » désigne une vidéo existante.

### Sécurité
- Linux : serveurs MCP locaux (stdio) lancés dans un bac à sable bubblewrap s’il est
  installé : système en lecture seule, dossier personnel, trousseau et D-Bus masqués ; seuls
  les dossiers confiés au serveur restent accessibles.
- `/docs` et `/redoc` retirés (scripts chargés depuis un CDN externe).

## [0.6.0] - 2026-10-12

### Ajouté
- Présentations Beamer (LaTeX rendu en PDF) : « fais un slide en beamer » ne donne plus un
  PowerPoint. Rédaction par sections en parallèle (plan, puis 3 à 5 diapositives détaillées
  par section avec schémas TikZ, exemples et code), compilation réelle, correction ciblée de
  la section fautive, et en dernier recours une section simplifiée plutôt qu’un échec. Essai :
  27 diapositives tirées d’un livre de 328 pages.
- Fiche compacte des longs documents joints (livres, cours) : plan, définitions, exemples et
  code de TOUT le document, calculés sur l’appareil sans modèle. Les créations s’en servent
  avec les passages les plus utiles, au lieu des seules premières pages ; en discussion, le
  plan accompagne les extraits.

### Corrigé
- Mode Apprendre : un quiz ou des fiches demandés sont toujours interactifs (un quiz écrit en
  texte est converti) et ne sont plus relus par un second modèle.
- « Fais un PowerPoint sur le livre » écrivait un livre : le format demandé prime.
- Plus de questions à choix après une réponse déjà donnée, ni pour une demande détaillée.
- « Équipe de modèles » s’appelle « Vérification par un second modèle ».

### Sécurité
- Adresse réellement connectée vérifiée (protection contre le « DNS rebinding »).
- Masquage des secrets élargi (Anthropic, OpenRouter, GitHub, Slack, AWS, JWT, clés privées…).
- Synchronisation : une conversation reçue est entièrement vérifiée avant d’être écrite
  (une conversation à moitié invalide ne peut plus effacer l’existante) ; les éléments
  refusés sont signalés.

## [0.5.9] - 2026-10-12

### Ajouté
- Orchestration multi-modèles : Réglages › Réponses › « Tâches en plusieurs parties » (Simple /
  Planifier / Plusieurs modèles). En « Plusieurs modèles », les parties d’une demande
  (« écris le code ; explique-le ; traduis… ») sont confiées en même temps à des modèles
  gratuits, celles qui dépendent d’une autre passent après avec son résultat, puis tout est
  réuni. Une demande simple suit le flux habituel. Aussi disponible par l’API
  (`orchestrate=true`), avec les mesures (durées, modèles). Désactivée par défaut.
- Réglages simples regroupés : Vous, Réponses, Mémoire, Espace de travail, Voix, Clés
  gratuites, Modèles payants, Affichage et langue.

### Sécurité
- Fichier de clés de repli (sans trousseau) chiffré, ancien fichier migré automatiquement.
- WebSockets limités (clients simultanés, tentatives par minute ; terminal : taille et débit
  des messages).
- MCP : interpréteurs de commandes, élévation de droits, outils destructeurs, code en ligne
  et variables dangereuses refusés ; tailles bornées ; depuis un autre appareil, serveurs
  HTTPS publics seulement. Audit dans `docs/SECURITY_AUDIT.md`.

### Corrigé
- « Artificial Analysis (classements) » traduit, sans « 0 modèle gratuit » trompeur.

## [0.5.8] - 2026-10-12

### Ajouté
- Notes 👍 / 👎 sous chaque réponse. Une note récompense ou pénalise le modèle pour ce type
  de demande (effet borné, visible dans « Pourquoi ce modèle »). Après un 👎 : raisons
  rapides (inexact, hors sujet, trop long…) et « Réessayer avec un autre modèle ». Une
  réponse 👎 n'est plus jamais réutilisée. Avec l'accord « Statistiques anonymes », seuls le
  modèle, le type de demande, la note et la raison sont partagés, jamais le texte. Chaque
  jour, les notes collectives (solde des appareils, à partir de 5) ajustent aussi le
  classement, plus faiblement. Script Supabase : `docs/stats/supabase_ratings.sql`.
- Pièces jointes de tous types : Word, PowerPoint, Excel, OpenDocument, epub, rtf, texte et
  code (md, csv, json, py…), archives zip et tar (contenu listé et lu), son et vidéo
  transcrits (piste son extraite par ffmpeg s'il est installé). Garde-fous : bombes zip,
  chemins sortants, liens symboliques et XML piégé refusés ; rien n'est exécuté.
- QR code vers le téléchargement : dans « À propos » (dernière version) et sur le poster de
  chaque version (page de cette version).

### Corrigé
- Le second modèle qui relit les réponses ne voyait pas les fichiers joints : il prenait
  leur contenu pour une invention. Il voit maintenant les documents et la fin du fil.
- Plus de questions à choix pour une demande de résumé (« résume ce fichier »).

## [0.5.7] - 2026-10-12

### Ajouté
- Réponses déjà données : la même question (même autrement formulée) reçoit une réponse
  immédiate, sans quota, marquée « Déjà répondu le … ». Jamais pour l’actualité, la météo,
  les prix, une question personnelle ou liée au fil, des nombres différents, une autre
  langue, une photo ou le mode Apprendre. Une question proche reçoit l’ancienne réponse comme
  aide, sans recopie. Régénérer contourne toujours le cache. Effacer une discussion efface
  ses réponses. Réglage et bouton Vider dans Personnalisation. Rien ne quitte l’appareil.
- Mémoire et cache réunis dans un même index local : les souvenirs sont retrouvés par le
  sens (accents, pluriels, autre tournure), plus seulement par les mêmes mots.
- 7 fournisseurs : Cerebras, SambaNova, GitHub Models, Together (modèles « Free ») gratuits
  avec clé ; Moonshot (Kimi), Qwen, Perplexity payants (seulement si leur prix est connu).
  Groq, Mistral, Gemini, NVIDIA et Hugging Face proposent maintenant tous leurs modèles
  dès que la clé est ajoutée. Adresses codées en dur : une liste en ligne ne peut jamais
  détourner une clé.
- Mode avancé :
  - fournisseurs personnalisés compatibles OpenAI : connexion testée avant l’ajout, HTTPS
    obligatoire et hôte épinglé ; HTTP seulement vers le réseau local, sans clé ;
  - fournisseurs exclus et enchaînements de modèles par type de demande ;
  - délais du routeur réglables dans des bornes sûres ;
  - export et import des réglages, jamais les clés.
  L’ajout de fournisseurs et l’import sont refusés depuis un client distant.
- Noms et descriptions des fournisseurs en anglais et en malgache.

## [0.5.6] - 2026-10-12

### Ajouté
- Questions à choix : pour une demande ouverte ou complexe, Tontolo pose d’abord une à
  quatre questions avec des puces à toucher, puis agit selon vos réponses. Pour un document
  ou un livre dont le public ou la longueur manquent, les questions sont immédiates, sans
  appel de modèle, et dans la langue de la demande. Aucune question pour une demande claire,
  une conversion ou en mode Apprendre. Un champ libre permet d’ajouter une précision.
- Longues discussions : seuls les 120 derniers messages s’ouvrent, les précédents se
  chargent avec « Messages précédents ».

### Corrigé
- Livres : une erreur LaTeX sans numéro de ligne faisait échouer tout le livre. Le chapitre
  fautif est maintenant retrouvé. S’il ne compile toujours pas après trois corrections, il
  est simplifié (texte et titres gardés) et le livre est livré.
- Demandes de création en malgache (« Manorata tatitra Word… », « amin’ny pdf ») reconnues.
- Un modèle qui « réfléchissait » sans fin pouvait bloquer une réponse plus de 10 minutes :
  après 150 s de réflexion sans texte (300 s pour une création), Tontolo passe au modèle
  suivant.
- En pleine discussion, plus de questions à choix pour une courte demande dont le contexte
  est déjà connu.

### Amélioré
- Le routeur mesure la vitesse réelle de chaque modèle (attente comprise) et favorise les
  plus rapides pour les échanges simples.
- Essais d’endurance documentés dans `docs/ENDURANCE.md` (bancs du cœur et essais réels).

## [0.5.5] - 2026-10-12

### Corrigé
- Corrections de fichiers : après une carte mentale, un document ou un PDF livré, un retour
  sans verbe (« excellent mais des vraies citations », « plus court », « en couleur »)
  corrige ce fichier. Avant, seules les demandes avec un verbe de modification étaient
  reconnues : le reste partait en discussion et la carte mentale était recopiée en texte.
- Deux versions d’un fichier ne portent plus le même nom : « …-v2 », « …-v3 », pour partager
  et enregistrer sans écraser.
- Demande de citations : plus de citation inventée. Seul ce dont le modèle est certain est
  mis entre guillemets, le reste est marqué « ≈ » (à vérifier).
- Certains modèles écrivaient leurs appels d’outils en texte (`<tool_call>…`) : ils sont
  maintenant exécutés et le balisage n’apparaît plus dans la réponse.

## [0.5.4] - 2026-10-12

### Ajouté
- Pastilles d’activité dans l’historique : orange « ? » = la discussion attend votre
  réponse (question du modèle, confirmation d’une action, accord pour un modèle payant) ;
  verte qui tourne = en cours sur cet appareil ; bleue « appareils » = en cours sur un autre
  appareil. Le menu porte un badge quand quelque chose se passe ailleurs que dans la
  discussion affichée.
- Quand une discussion attend votre réponse pendant que vous êtes ailleurs : bandeau
  « Ouvrir » (application ouverte) ou notification (arrière-plan).

## [0.5.3] - 2026-10-12

### Ajouté
- Livres et longs documents : « Génère un livre de 200 pages sur… » (ou « je veux un livre
  de… ») établit un plan, rédige les chapitres en parallèle sur plusieurs modèles, compile
  le PDF et corrige seulement le chapitre fautif. Livré en PDF, ou en archive .zip (un
  fichier par chapitre + PDF) si plusieurs fichiers sont demandés. Le plan et chaque
  chapitre apparaissent dans « Résultats intermédiaires » dès qu’ils sont écrits ; un
  chapitre muet est réessayé puis marqué « à refaire » au lieu de perdre le livre.
- Poster de version illustré (français, anglais, malgache), montré dans « Nouveautés » et
  joint à chaque release.
- Sélecteur Général / Apprendre / Agent : seul le mode actif affiche son nom.
- Accueil : salutations malgaches selon l’heure (Salama, Manao ahoana).

### Corrigé
- Tontolo ne demande plus « puis-je écrire un fichier ? » pour un fichier qui n’était jamais
  livré : sans dossier de travail choisi, l’agent n’a plus d’outil d’écriture ; les fichiers
  demandés passent par la création de fichiers.
- Accueil : le prénom s’affiche dès le démarrage à froid.

### Sécurité
- Terminal : jeton obligatoire, processus fils récoltés. Navigateur de l’agent : jamais
  l’API de Tontolo ni les métadonnées cloud. Créations synchronisées : type de contenu
  validé, pages actives servies en téléchargement (CSP sandbox, nosniff). LaTeX : lecture et
  exécution de fichiers refusées (\\openin5, \\read, \\InputIfFileExists…). Plafond global
  de 300 Mo pour les résultats de tâches.

## [0.5.2] - 2026-10-12

### Ajouté
- Accueil d’une nouvelle discussion vivant : salutation selon l’heure suivie du prénom de
  l’utilisateur (réglage « Votre prénom », compte Google/GitHub, ou prénom donné dans une
  discussion), écrite lettre par lettre ; quatre suggestions qui changent selon l’heure, le
  jour, le mode et la dernière discussion (« Reprendre … »). Animations coupées avec
  « Réduire les animations ».
- Réglages › Avancé › Stockage : place occupée par type de données et bouton « Vider » le
  cache (aucune donnée effacée).

### Amélioré
- Espace disque : tous les caches dans un seul dossier, sans doublons. Une seule mise à jour
  téléchargée est gardée (les anciennes, jusqu’à 55 Mo chacune, étaient conservées en double),
  fichiers temporaires effacés après un jour, cache du navigateur de l’agent plafonné.

## [0.5.1] - 2026-10-11

### Ajouté
- Modèles : liste plus claire, fiche détaillée (fournisseur, coût, contexte, capacités,
  scores, vitesse, état) et badge « Agent » ; liste simple des générateurs d’images, de
  vidéos et de sons avec leur état.
- Mode Agent (troisième onglet) et agents prêts : Chercheur, Développeur, Rédacteur,
  Analyste. Gratuits par défaut ; modèles payants au choix (jamais / sur accord / auto).
- Tâches complexes : plan en étapes, parties indépendantes confiées en même temps à
  plusieurs modèles, ou livraison pas à pas avec « Continuer ». Le plan reste dans le fil.
- Compactage des longues discussions en fiche structurée (sujets, faits, décisions,
  créations, tâches), automatique et désactivable, ou à la demande ; messages conservés.
- Réponse coupée par la limite de longueur : suite demandée automatiquement (3 fois au
  plus, arrêt si rien de nouveau), aussi pour les longs fichiers.
- Plusieurs fichiers demandés (ex. livre LaTeX en chapitres) : livrés dans une archive .zip ;
  un livre LaTeX est compilé en entier et son PDF ajouté.
- Bureau Linux : dossier de travail choisi pour l’agent (lecture, recherche, modification
  avec différence affichée, sauvegarde et annulation), commandes confirmées une à une,
  chemins sensibles bloqués ; terminal intégré (une session par discussion).
- Navigateur intégré piloté par l’agent : vrai navigateur Chromium/Chrome/Brave/Vivaldi
  sur le bureau (profil dédié), panneau WebView sur tablette ; un onglet par discussion.
  L’agent lit la page, la voit (capture décrite par un modèle à vision), suit les liens ;
  un bouton (envoi, achat, suppression) ou une saisie demande votre accord.
- Terminal lisible par l’agent (une session par discussion, tenue par le cœur) ; il peut y
  taper après confirmation, et ses commandes y apparaissent.
- Résultats intermédiaires des tâches complexes (parties, étapes, sorties longues,
  brouillons de fichiers) gardés sur l’appareil 7 jours après la fin de la tâche, visibles
  (« Voir les étapes ») et synchronisés chiffrés : le fil tient même après compactage.
- Dossiers : partage du contexte activable dossier par dossier (désactivé par défaut).
- Synchronisation : créations de 1 Mo au plus (chiffrées), tâches en cours visibles sur les
  autres appareils, cycle de 20 s quand l’application est ouverte.
- Règle de version : chaque chiffre de 0 à 9 (0.2.9 → 0.3.0, 0.9.9 → 1.0.0), script et
  contrôles automatiques.

### Corrigé
- Android : la réponse continue quand on quitte l’application ; au retour, Tontolo se
  rattache au tour en cours au lieu d’annoncer une connexion coupée.
- « Convertis ce HTML en PDF » (et toute conversion de fichier) utilise enfin le document
  joint ou le dernier fichier créé.
- Les souvenirs automatiques ne servaient plus jamais : ils sont rappelés dans leur propre
  discussion.

### Sécurité
- Secrets (clés d’API, jetons, mots de passe, clés privées) masqués avant d’être envoyés à
  un modèle ; terminal accessible uniquement à l’application locale ; liens symboliques et
  dossiers cachés refusés dans le dossier de travail ; deux discussions en parallèle ne
  partagent jamais un onglet ou un terminal.

### Compatibilité
- Même signature, paquet Android, noms de téléchargements et table de synchronisation ; les
  nouveaux éléments synchronisés sont ignorés par les versions précédentes.

## [0.5.0] - 2026-10-11

### Corrigé
- Discussions isolées : les dossiers organisent les fils sans injecter les résumés d’autres
  discussions. Les chargements tardifs de messages, documents et retouches sont ignorés
  après un changement de discussion.
- Mémoire : les souvenirs explicitement enregistrés restent disponibles entre discussions ;
  les captures automatiques restent rattachées à leur fil. Fusion par origine et catégorie,
  compactage sérialisé avec les captures et suppressions, provenance et identifiants conservés.
  Les anciens souvenirs dont le compactage avait perdu la provenance restent consultables,
  mais ne sont plus injectés automatiquement dans d’autres fils.
- Image → vidéo : les animations de photos jointes sont reconnues ; les créations réelles du
  fil servent à comprendre les relances. L’image source doit appartenir au même fil ; une
  image échouée ne provoque plus le retour silencieux à une ancienne réussite.
- Une demande de nouvelle vidéo depuis du texte ne reprend plus une ancienne image.
  Les consignes de mouvement sont conservées pendant la traduction, avec délai borné.
- Image manquante : message explicite en français, anglais et malagasy ; aucune vidéo lancée
  depuis du texte à la place de l’image demandée. Régénération testée avec la même source.
- Les résumés terminés après une modification ou suppression du fil ne sont plus appliqués.
  Les modifications et régénérations sont refusées pendant une réponse en cours.

### Compatibilité
- Même signature, paquet Android, schéma de stockage et noms de téléchargements.
- Les quotas du fournisseur vidéo gratuit restent applicables : aucune garantie de GPU
  disponible ni de résultat fidèle à 100 % ; les échecs et délais de retour restent affichés.


## [0.4.7] - 2026-10-11

### Corrigé
- Connexion Google et GitHub sur Android : retour directement dans Tontolo par lien
  dédié, sans serveur localhost. Le vérificateur PKCE est conservé temporairement
  dans le stockage sécurisé pour reprendre après un redémarrage de l’application.
- Linux : les requêtes parasites (favicon, retour sans code) ne terminent plus
  l’attente de connexion. Échange du code limité à 20 secondes.
- Validation stricte du lien de retour, refus des jetons implicites, double connexion
  empêchée. Aucun changement de signature, de paquet ni de schéma de base.

### Configuration serveur
- Ajouter `io.github.raantss18.tontolo://login-callback/` aux Redirect URLs Supabase.
  Garder `http://localhost:43823/` pour Linux et les anciennes versions Android.


## [0.4.6] - 2026-10-11

### Corrigé (retour d'utilisateur)
- Une photo d'exercice envoyée dans une discussion recevait la réponse à l'exercice d'une AUTRE
  discussion : la mémoire injectait des souvenirs sans rapport (dont des tâches ponctuelles
  d'autres discussions). Elle n'injecte plus que les souvenirs liés à la demande (et jamais
  ceux tirés de la discussion en cours) et n'enregistre plus les tâches ponctuelles.

### Ajouté
- **Priorités du contexte** : 1) le fil de la discussion fait foi (réponse toujours à la
  dernière demande, photo jointe comprise, même après un changement de modèle), 2) les autres
  discussions du même dossier (titres et résumés) en contexte secondaire, 3) la mémoire en
  dernier.
- **Longues discussions** (texte, images, vidéos, fichiers) : résumé du début du fil tenu à
  jour en arrière-plan et enregistré, derniers messages toujours envoyés mot pour mot ; seules
  les 2 dernières photos sont renvoyées en image ; chaque création est décrite par sa demande.

## [0.4.5] - 2026-10-11

### Corrigé
- Création de fichier en échec quand le modèle rédacteur tardait ou devenait indisponible : un
  second essai est fait automatiquement (le routeur choisit un autre modèle) ; en cas d'échec, la
  cause est affichée sous le message.
- CI de publication : 3 essais pour l'empaquetage du cœur Python (téléchargements coupés qui
  avaient fait échouer les publications 0.4.2 et 0.4.3, dont le contenu est inclus ici).

## [0.4.4] - 2026-10-11

### Corrigé (retours d'utilisateurs)
- Photo d'un exercice + « traite l'exercice 8… rends la réponse en pdf » : la demande était prise
  pour une retouche (« rends ») et une image sans rapport était créée. Une tâche sur le contenu
  d'une photo (exercice, question, « résous », « explique »…) n'est plus jamais une retouche ;
  photo + demande de fichier : la photo est d'abord lue (transcription par un modèle qui voit,
  même si elle est tournée), puis le fichier est rédigé, vérifié et corrigé.
- « Nombre maximal d'étapes atteint » sur une question simple : quand un modèle enchaîne les
  recherches, Tontolo répond au dernier tour avec ce qui a été trouvé au lieu d'échouer, et un
  appel d'outil identique n'est plus répété.

## [0.4.3] - 2026-10-11

### Corrigé (retours d'utilisateur)
- Photo + « Put this on a public space in Antananarivo » : la demande de modification n'était
  pas reconnue (« put / place / insert / pose / incruste… ») et partait vers un modèle de texte.
- « Anime-la » / « animate it » juste après une image : la vidéo part maintenant de cette image
  (elle était créée à partir du texte seul, sans rapport avec l'image).
- « Rajoute des détails et des exemples » juste après une carte mentale (ou tout fichier créé) :
  le même fichier est refait à partir de sa version précédente, au lieu d'une réponse en texte.
- La photo jointe clignotait dans la bulle pendant l'écriture de la réponse.

### Ajouté
- **Retouche fidèle gratuite** avec FLUX.1 Kontext (Space Hugging Face) : la personne ou l'objet
  est conservé et seule la scène change ; repli sur la réinterprétation si le quota GPU est
  épuisé.

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
