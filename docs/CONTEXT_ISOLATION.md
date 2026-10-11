# Isolation du contexte — 0.5.0

Un dossier sert au rangement. Il ne donne pas au modèle accès aux autres discussions.
Le fil ouvert, ses documents et ses créations restent le contexte principal.

## Mémoire

- « Souviens-toi… / Remember… / Tadidio… » enregistre un souvenir explicite partageable.
- Les souvenirs ajoutés manuellement dans les réglages restent partageables.
- Une extraction automatique conserve le fil d'origine ; elle ne devient pas une consigne
  pour une autre discussion. Le fil garde ses propres messages et résumés.
- La fusion compare aussi l'origine et la catégorie ; le compactage conserve ces champs
  et les identifiants des éléments retenus. Captures, compactage et suppressions sont sérialisés.
- Les anciennes lignes « compactage », dont l'origine avait été effacée, sont conservées
  et consultables, mais ne sont pas rappelées automatiquement. Pour rendre un ancien
  souvenir global, l'enregistrer explicitement ou l'ajouter dans les réglages.

## Image → vidéo

Créer une image puis demander « anime-la », « transforme cette image en vidéo »,
« animate it » ou joindre une photo avec « ampihetsiho ». Le job vidéo conserve
`source_job_id` quand il vient d'une création et `input_mode` (image ou texte).

L'image doit appartenir à cette discussion et être disponible. Un échec de la dernière
création bloque le retour silencieux à une ancienne image. Sans source, l'application
invite à joindre une photo ou régénérer l'image ; elle ne produit pas une vidéo texte
à la place. Une nouvelle demande vidéo sans référence explicite part du texte seul.

Les fonctions et l'ordre des paramètres du Space LTX officiel ont été vérifiés via sa
configuration publique le 2026-10-11. Tests de transport Gradio simulés : upload, mode
image-to-video et ratio portrait. Les essais automatiques ne prouvent pas la disponibilité
permanente du GPU gratuit ni la fidélité visuelle du modèle.

## Frontières testées

Tests cœur : marqueur d'un autre fil, image échouée, nouvelle scène courte sans héritage,
photo animée dans trois langues, régénération avec la même source, nouvelle vidéo texte,
souvenirs de deux fils identiques, compactage concurrent, résumés invalidés après modification
ou suppression, dossier avec plusieurs fils, ouverture d'une base 0.2.0.

Tests interface : ouverture B avant la fin du chargement A ; nouvelle discussion pendant
le chargement d'un résultat média. Les retours tardifs ne modifient plus l'écran courant.

Aucune modification de signature, paquet Android, OAuth ou schéma de base nécessaire.


Validation finale locale : 203 tests cœur, 47 tests Flutter, analyse et typage propres ;
installation signée par-dessus 0.4.7 réussie. Essai réel LTX avec une image synthétique :
refus « quota GPU gratuit épuisé » correctement classé, donc aucun résultat vidéo réel
validé lors de cet essai. Contrôles GitHub réussis sous Python 3.11/3.14, cœur minimal et Flutter.

Publication v0.5.0 confirmée : workflow 38166719297 réussi, sept fichiers disponibles,
téléchargements en tête des notes. Empreinte SHA-256 et installation de l’APK officiel
x86_64 vérifiées (versionCode 4023, sans effacement). Trois APK 26,2–27,7 Mo ; AppImage
47,4 Mo. Les discussions de l’émulateur restent visibles après la mise à jour.
