
### Quel fichier choisir ?

**Android** — Android 7.0 ou plus récent (testé sur Android 10 et Android 16)

| Fichier | Pour quels appareils |
|---|---|
| `tontolo-…-arm64-v8a.apk` | **Le bon choix dans 95 % des cas.** Processeurs ARM 64 bits (« ARMv8 ») : presque tous les téléphones et tablettes depuis 2016 — Samsung Galaxy, Xiaomi / Redmi / POCO, Google Pixel, OnePlus, Oppo, Realme, Huawei, Honor, Motorola… **Fonctionne de Android 7 à Android 16.** |
| `tontolo-…-armeabi-v7a.apk` | Processeurs ARM 32 bits : appareils anciens ou d'entrée de gamme (avant ~2016) ou système installé en 32 bits. Android 7 et plus. |
| `tontolo-…-x86_64.apk` | Processeurs Intel/AMD : émulateurs Android (Android Studio), Chromebooks, tablettes ou PC sous Android x86. |

*Un doute ?* Prenez `arm64-v8a`. Si Android répond « application non compatible », prenez `armeabi-v7a`.
Les mises à jour suivantes se proposent ensuite dans l'application elle-même (Réglages › Nouveautés), avec le résumé des changements.

**Linux**

| Fichier | Pour quels systèmes |
|---|---|
| `Tontolo-…-x86_64.AppImage` | PC 64 bits Intel/AMD, distribution récente (glibc ≥ 2.35 : Ubuntu 22.04+, Debian 12+, Fedora 36+, Arch, openSUSE récent…) avec GTK 3. `chmod +x` puis double-clic. |
| `tontolo-….whl` / `.tar.gz` | Ligne de commande et serveur compatible OpenAI sur Linux, macOS ou Windows avec Python ≥ 3.11 : `pip install tontolo-….whl`. |

> Les APK ont été exécutés sur émulateur (x86_64, Android 10 et 16) ; les versions ARM sont construites avec le même code mais n'ont pas encore été essayées sur un appareil réel — signalez tout problème dans les *issues*.
