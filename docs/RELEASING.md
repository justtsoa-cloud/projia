# Publier une version

Une release GitHub complète est produite automatiquement par
`.github/workflows/release.yml` à chaque tag `vX.Y.Z`.

## Règle de version

Chaque chiffre va de 0 à 9 : après `x.y.9` vient `x.(y+1).0`, après `x.9.9` vient
`(x+1).0.0` (ex. 0.2.9 → 0.3.0, 0.9.9 → 1.0.0). Un saut volontaire au palier supérieur
reste permis (0.4.7 → 0.5.0), jamais un chiffre à 10 ni un retour en arrière. La CI vérifie
la cohérence des fichiers, et la release refuse une étiquette qui ne suit pas la règle.

## Étapes

1. `python3 scripts/bump_version.py` (version suivante) ou `… 0.6.0` (saut permis) : met à
   jour `core/pyproject.toml`, `core/tontolo/__init__.py`, `app/lib/core/updater.dart` et
   `app/pubspec.yaml` (numéro de build Android +1).
2. Compléter `CHANGELOG.md` (section `## [X.Y.Z] - AAAA-MM-JJ`) et les nouveautés fr/en/mg
   de `app/lib/core/whats_new.dart`, puis lancer les tests du cœur et de Flutter.
   Préparer aussi le **poster de la version** : simple mais complet, illustré, avec le
   changement majeur montré par un exemple concret d'utilisation (demande consigne du
   propriétaire, 2026-10-12).
3. `git commit -m "chore(release): vX.Y.Z"` puis `git tag vX.Y.Z && git push --tags`.
4. La CI construit et publie : roue + sdist Python, AppImage (x86_64), APK par ABI
   (arm64-v8a, armeabi-v7a, x86_64) signés, `SHA256SUMS`, rapport de taille, notes tirées
   du CHANGELOG. **La release est bloquée si un contrôle échoue** (lint, typage, tests,
   budgets de taille).

## Secrets GitHub à créer (Settings › Secrets and variables › Actions)

| Secret | Contenu |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | Keystore de signature encodé en base64 (`base64 -w0 tontolo.jks`) |
| `ANDROID_KEYSTORE_PASSWORD` | Mot de passe du keystore |
| `ANDROID_KEY_ALIAS` | Alias de la clé |
| `ANDROID_KEY_PASSWORD` | Mot de passe de la clé |

Créer un keystore :

```bash
keytool -genkeypair -v -keystore tontolo.jks -keyalg RSA -keysize 4096 -validity 10000 -alias tontolo
```

Pour signer une version locale avec la même clé (sinon Android refuse la mise à jour
d'une version officielle) : `set -a; source release-keys/signing.env; set +a` avant
`flutter build apk` (le dossier `release-keys/` est ignoré par Git).

**Conservez le keystore hors du dépôt et sauvegardez-le** : sans lui, les mises à jour
Android ne pourront plus s'installer par-dessus l'application existante.
Sans ces secrets, la CI signe les APK avec une clé de débogage (avertissement dans les notes).

## Vérifier une release

```bash
sha256sum -c SHA256SUMS --ignore-missing
```


## Alerte Google Play Protect (« analyse recommandée »)

Elle s'affiche pour les APK installés hors du Play Store et inconnus de Google. Le code ne peut
pas la supprimer ; ce qui la fait disparaître dépend du propriétaire du compte développeur :

1. **Vérification développeur Android** (Android Developer Console) : enregistrer l'identité du
   développeur, le nom de paquet `io.github.raantss18.tontolo` et l'empreinte du certificat de
   signature de `release-keys/tontolo.jks`. Google l'impose progressivement pour l'installation
   hors Play Store sur les appareils certifiés ; une fois l'application enregistrée, l'alerte
   « inconnue » n'a plus lieu d'être.
2. **Publication sur Google Play** (même en test interne ou fermé) : Google analyse et connaît
   alors l'application.
3. Dans tous les cas : **ne jamais changer de clé de signature ni de nom de paquet**, sinon
   l'application redevient « inconnue » et les mises à jour ne s'installent plus par-dessus.

Empreinte du certificat à déclarer :

```bash
keytool -list -v -keystore release-keys/tontolo.jks | grep SHA256
```

Ces démarches demandent un compte Google du propriétaire (et éventuellement des frais
d'inscription Play) : elles ne sont pas automatisées dans ce dépôt.


## Compatibilité des mises à jour (saut de versions)

Toute version installée depuis la **0.2.0** doit pouvoir passer directement à la dernière.
Ces invariants sont vérifiés par la CI (`release.yml`) et par les tests :

- noms des fichiers : `tontolo-<v>-<abi>.apk`, `Tontolo-<v>-<arch>.AppImage`, `SHA256SUMS` ;
- même clé de signature et même nom de paquet Android ; numéro de build (`+N` de
  `pubspec.yaml`) strictement croissant ;
- une section `## [<v>]` dans `CHANGELOG.md` et des nouveautés dans `whats_new.dart` ;
- base de données : migrations additives uniquement (`core/tests/test_upgrade.py` ouvre une
  base créée par la 0.2.0).

L'application cherche la dernière release par l'API GitHub, puis, si l'API refuse (limite de
60 requêtes/heure par adresse IP, fréquente sur réseau mobile), par la redirection de
`/releases/latest` ; elle présente ensuite toutes les notes des versions sautées.
