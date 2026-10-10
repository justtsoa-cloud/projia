# Journal des modifications

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement
[SemVer](https://semver.org/lang/fr/).

## [Non publié]

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
