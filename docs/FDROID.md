# F-Droid : faisabilité et marche à suivre (étude du 2026-10-18)

Verdict : **possible, mais pas immédiat**. Rien dans Tontolo n'est contraire à la philosophie de
F-Droid (aucun service Google, aucune pub, aucun traqueur, Apache-2.0), mais le dépôt exige une
construction **entièrement depuis les sources**, et c'est le point à travailler.

## Ce qui est déjà conforme
- Licence Apache-2.0 ; dépendances Dart toutes permissives (`scripts/check_flutter_licenses.py`,
  seule exception documentée : `dbus`, MPL-2.0 non modifié, uniquement sous Linux).
- Aucune dépendance Google Play Services, Firebase ni publicité (vérifié dans `app/pubspec.yaml`).
- Statistiques minimales et facultatives (désactivables) ; retours et rappels en option.
- Métadonnées prêtes : `fdroid/metadata/` (description courte/longue fr/en/mg).

## Anti-fonctionnalités à déclarer (`AntiFeatures`)
- **NonFreeNet** : l'application appelle des services en ligne (modèles gratuits, compilation
  LaTeX en ligne, flux d'actualités si le rappel est accepté) ; rien n'est obligatoire.
- **NonFreeAssets** : aucun connu (logo et affiches sous la licence du dépôt) ; à re-vérifier.

## Points bloquants à résoudre avant de soumettre
1. **Cœur Python** : `serious_python` télécharge des binaires CPython et des roues PyPI
   précompilées au moment de `scripts/package_python.sh`. F-Droid refuse les binaires non
   construits depuis les sources : il faut soit vendre les sources et les compiler dans la recette
   (CPython pour Android + `pydantic-core`, `cryptography`… écrits en Rust), soit réduire le cœur
   Android aux paquets en Python pur. C'est le gros chantier (plusieurs jours, à tester sur un
   serveur de construction propre).
2. **Reproductibilité** : épingler Flutter (`~/development/flutter`, version exacte), le SDK
   Android et `uv.lock` ; signer avec la clé de F-Droid ou la reproductibilité vérifiée.
3. **Clé de mise à jour intégrée** : sur F-Droid, les mises à jour passent par le dépôt ; la mise
   à jour intégrée (APK signé par `update-signing.pub`) doit être désactivée dans cette variante
   (réglage de construction à créer, par exemple `TONTOLO_STORE=fdroid`).

## Marche à suivre (à faire par l'auteur)
1. Résoudre le point 1 sur une machine propre (`fdroid build -v -l io.github.raantss18.tontolo`).
2. Copier `fdroid/metadata/` vers un fork de `fdroiddata`, écrire
   `metadata/io.github.raantss18.tontolo.yml` (Categories: Internet, Science & Education ;
   License: Apache-2.0 ; SourceCode/IssueTracker : dépôt GitHub ; AutoUpdateMode: Version).
3. Ouvrir la demande de fusion sur gitlab.com/fdroid/fdroiddata.

Flatpak (optionnel) : la compilation locale LaTeX et les commandes de l'agent reposent sur
bubblewrap, difficile dans un bac à sable Flatpak ; sous Flatpak ces fonctions retombent sur le
refus (déjà géré par `tontolo/sandbox.py`) et les services en ligne. Non entrepris.
