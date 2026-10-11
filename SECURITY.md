# Politique de sécurité

## Signaler une vulnérabilité

Merci de **ne pas ouvrir d'issue publique**. Utilisez le signalement privé de GitHub
(onglet *Security* › *Report a vulnerability*) du dépôt `raantss18/tontolo`.
Nous accusons réception sous 7 jours.

## Périmètre

- fuite de clés API (stockage, journaux, réseau) ;
- contournement du jeton du serveur local ou distant ;
- exécution de code via les outils de l'agent, le contenu web ou MCP (injection de prompt) ;
- mises à jour : contournement de la vérification SHA-256.

Versions prises en charge : la dernière version publiée.

Contact de l'auteur : RANIRIAMANJAKA Antsa — antsa.raniriamanjaka@univ-antananarivo.mg.

## Audits

### 2026-10-11 (v0.2.10)
Outils : `bandit`, `pip-audit` (aucune vulnérabilité connue dans les dépendances), revue
manuelle. Corrigé :
- flux XML distant (nouveaux modèles) : DTD et entités refusées avant analyse (attaque
  « billion laughs » / entités externes) ;
- vidéo (Space Hugging Face) : téléchargement **sans redirection** (la clé Hugging Face ne
  quitte jamais le domaine du Space), taille plafonnée pendant le téléchargement, URL limitée
  au domaine du Space ;
- retouche locale : dimensions vérifiées avant décodage (image piégée de plusieurs gigapixels) ;
- `PUT /tontolo/settings` : le dossier de travail des outils de l'agent n'est plus modifiable à
  distance (comme la configuration du serveur) ;
- statistiques anonymes : base en insertion seule (RLS), contraintes de taille, aucune donnée
  de contenu ; désactivables.
Vérifié sans changement nécessaire : jeton comparé à temps constant sur toutes les routes
(sauf `/health`), contrôles Origin/Host (CSRF, DNS rebinding), clés en stockage chiffré,
HTTPS obligatoire pour les clés, mises à jour vérifiées par SHA-256 et origine GitHub,
liens ouverts limités à http(s), récepteurs Android non exportés, sauvegarde Android désactivée.
