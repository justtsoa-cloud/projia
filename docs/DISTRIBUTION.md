# Publier Tontolo : Play Store, F-Droid, dépôts Linux

Aujourd'hui Tontolo est distribué par les **releases GitHub** (APK par ABI, AppImage, roue
Python) avec mise à jour intégrée. Ce guide explique comment l'ajouter aux boutiques et
dépôts, ce qu'il faut changer dans le projet pour chacun, et dans quel ordre s'y prendre.
Les chiffres marqués *(à vérifier)* évoluent : contrôlez-les le jour de la démarche.

## Résumé et ordre conseillé

| Canal | Coût | Difficulté | Délai | Conseil |
|---|---|---|---|---|
| IzzyOnDroid (dépôt F-Droid) | gratuit | faible | quelques jours | **1ʳᵉ étape** : réutilise les APK des releases |
| AUR (Arch, Manjaro, EndeavourOS) | gratuit | faible | immédiat | **2ᵉ étape** : paquet `tontolo-bin` prêt dans `packaging/aur/` |
| PyPI (cœur en ligne de commande) | gratuit | faible | immédiat | `pipx install tontolo` |
| Google Play | 25 $ une fois *(à vérifier)* | moyenne | 2 à 4 semaines (test fermé) | fait disparaître l'alerte Play Protect |
| Flathub | gratuit | élevée | semaines | après stabilisation (build depuis les sources) |
| F-Droid officiel | gratuit | élevée | mois | bloqué par le Python prébuilt (voir plus bas) |
| Snap Store | gratuit | moyenne | jours | optionnel |

## 1. Google Play

**Prérequis** : compte Google Play Console (frais uniques, vérification d'identité avec pièce
officielle ; compte « personnel » ou « organisation »).

**Règle des comptes personnels récents** *(à vérifier)* : avant la production, un **test
fermé avec au moins 12 testeurs pendant 14 jours d'affilée** est obligatoire. Prévoir une
liste de testeurs (élèves, collègues) dès le début.

**Changements nécessaires dans le projet**
1. **Canal « play »** : ajouter `--dart-define=TONTOLO_CHANNEL=play` et, dans ce canal,
   **désactiver la mise à jour intégrée** (règle Play : une application ne se met pas à jour
   elle-même hors Play) et **retirer la permission `REQUEST_INSTALL_PACKAGES`** (permission
   restreinte sur Play). Le plus propre : une *flavor* Gradle `play` avec un manifeste qui
   supprime la permission (`tools:node="remove"`). *À implémenter avant la soumission.*
2. **Format AAB** : `flutter build appbundle --release` (le Play Store génère les APK par
   appareil). Activer **Play App Signing** et téléverser la clé d'importation ; la clé de
   release actuelle peut servir de clé d'importation pour garder la même identité.
3. **API cible** : Play impose une API récente *(à vérifier : 35 en 2025, 36 attendue)*.

**Fiche et formulaires**
- Textes (titre ≤ 30 caractères, description courte ≤ 80, longue ≤ 4000) : repartir de
  `fastlane/metadata/android/fr-FR/` et `en-US/`.
- Visuels : icône 512×512 (`docs/brand/tontolo-icon-512.png`), bannière 1024×500, au moins
  2 captures téléphone (`docs/screenshots/`).
- **Politique de confidentialité** : URL publique obligatoire (ex. page GitHub Pages reprenant
  `docs/COMPLIANCE.md`).
- **Sécurité des données** : déclarer
  - les statistiques anonymes (identifiant d'installation aléatoire, version, langue, pays de
    la langue, nombre de messages) — désactivables ;
  - les messages envoyés aux fournisseurs d'IA choisis (traités par des tiers, chiffrés en
    transit) ;
  - les comptes (adresse e-mail via Google/GitHub) et la synchronisation chiffrée de bout en
    bout — facultatifs ;
  - l'enregistrement audio (dictée), utilisé seulement à la demande.
- **IA générative** : déclarer la génération de texte/images, et le signalement de contenu
  (bouton de signalement ou adresse de contact).
- Classification du contenu (questionnaire IARC), public cible (préciser si l'application
  vise des moins de 13 ans : le mode Apprendre s'adresse aussi aux élèves → règles
  « Familles » plus strictes ; plus simple de cibler 13 ans et plus).

**Bénéfice** : plus d'alerte Play Protect, mises à jour par le Play Store.

## 2. F-Droid

### IzzyOnDroid (recommandé d'abord)
Dépôt compatible F-Droid qui **reprend les APK des releases GitHub** (pas de rebuild).
1. Ouvrir une demande sur le dépôt IzzyOnDroid (GitLab « IzzyOnDroid/repo », *issue* « New
   app ») avec le lien du dépôt GitHub.
2. Exigences : application libre (Apache-2.0 ✔), APK signés de façon stable ✔, taille
   raisonnable par APK *(à vérifier : ≈ 30 Mo)* ✔ (≈ 26 Mo par ABI).
3. Anti-fonctions signalées probables : *NonFreeNet* (services d'IA en ligne non libres) et
   *Tracking* si les statistiques sont actives. La mise à jour intégrée doit pouvoir être
   désactivée : prévoir un canal `fdroid` comme pour Play.
4. Les métadonnées sont lues dans `fastlane/metadata/android/` (déjà présent).

### F-Droid officiel (plus tard)
F-Droid **reconstruit l'application depuis les sources** sur ses serveurs, sans binaire
prébuilt. Points bloquants actuels :
- **serious_python télécharge un Python 3.14 prébuilt** pendant le build : il faudra le
  compiler depuis les sources dans la recette (scripts `srclibs`/`prebuild`), travail notable ;
- statistiques et mise à jour intégrée à désactiver (build sans `--dart-define` de stats =
  statistiques déjà inertes) ;
- Flutter doit être fourni via `srclibs: flutter@stable`.
Une recette d'exemple est dans `packaging/fdroid/io.github.raantss18.tontolo.yml` (à
soumettre en *merge request* au dépôt `fdroiddata` quand les points ci-dessus sont réglés).

## 3. Linux

### AUR (le plus simple)
Paquet binaire `tontolo-bin` construit à partir de l'AppImage de la release :
`packaging/aur/PKGBUILD` et `.SRCINFO`.
1. Créer un compte sur aur.archlinux.org et y déposer sa clé SSH.
2. `git clone ssh://aur@aur.archlinux.org/tontolo-bin.git`, copier les deux fichiers.
3. À chaque version : mettre à jour `pkgver`, la somme `sha256sums` (dans `SHA256SUMS` de la
   release), puis `makepkg --printsrcinfo > .SRCINFO`, `makepkg -si` pour tester, `git push`.

### Flathub
Flathub exige en pratique un **build depuis les sources** pour une application libre (le
réemballage d'une AppImage n'est pas accepté ; `extra-data` est réservé aux logiciels non
libres). Étapes :
1. Écrire un manifeste qui construit Flutter et le cœur Python depuis les sources (modules
   `flutter`, `python3`, dépendances pip via `flatpak-pip-generator`).
2. Fichiers AppStream fournis : `packaging/flatpak/io.github.raantss18.tontolo.metainfo.xml`
   et `.desktop` (valider avec `appstreamcli validate` et `desktop-file-validate`).
3. Ouvrir une *pull request* sur `flathub/flathub` (branche `new-pr`), revue par l'équipe.
Réaliste après la 0.3.x, une fois le build reproductible.

### Snap Store
`snapcraft` peut empaqueter le bundle Linux (`flutter build linux`) avec l'extension
`gnome`. Compte Ubuntu One, `snapcraft register tontolo`, puis `snapcraft upload`.
Confinement strict : prévoir les *plugs* `network`, `audio-record`, `home`.

### Paquet .deb (optionnel)
Le bundle `build/linux/x64/release/bundle` peut être empaqueté avec `dpkg-deb` (dossier
`/opt/tontolo` + fichier `.desktop` + icône) et ajouté aux assets de release par la CI.

### PyPI (cœur en ligne de commande et serveur compatible OpenAI)
1. Créer le projet sur pypi.org et configurer la **publication de confiance** (*Trusted
   Publishing*) pour le dépôt GitHub et le workflow `release.yml`.
2. Ajouter à la CI une étape `pypa/gh-action-pypi-publish` qui publie la roue `core/dist/*`.
3. Ensuite : `pipx install tontolo` puis `tontolo serve`.

## Rappels communs
- **Même clé de signature Android partout** (GitHub, IzzyOnDroid) pour que les mises à jour
  s'installent par-dessus ; Play utilise sa propre clé de distribution (Play App Signing),
  donc on ne passe pas d'une installation GitHub à une installation Play sans désinstaller.
- **Numéro de build strictement croissant** (déjà vérifié par la CI).
- Captures et textes dans les trois langues (fr, en, mg) quand la boutique le permet.
