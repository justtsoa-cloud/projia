# Journal des modifications

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement
[SemVer](https://semver.org/lang/fr/).

## [Non publié]

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
