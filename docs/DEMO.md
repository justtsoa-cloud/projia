# Captures et vidéos de démonstration

Les visuels de présentation sont produits sans toucher à votre session :

- **Android** : émulateur (`avdmanager`/`emulator`), captures par `adb exec-out screencap`,
  vidéos par `adb shell screenrecord`, montage avec `ffmpeg` (sous-titres, écran de fin).
- **Bureau** : `app/demo/desktop_demo_test.dart` fait tourner la vraie interface en 1440×900
  dans un banc d'essai Flutter, branchée sur un vrai moteur local (`projia serve`), et
  enregistre ses images.

```bash
# moteur local isolé
cd core && PROJIA_HOME=/tmp/projia-demo .venv/bin/projia serve --port 8777 &
# banc d'essai (images dans /tmp/projia_frames, captures dans /tmp/projia_stills)
cd app && flutter test demo/desktop_demo_test.dart
# DEMO_IMAGE=1 ajoute la scène de création d'image (si le service gratuit répond)
```

Les fichiers générés vont dans `press/` (non versionné) ; seules les captures du README sont
conservées dans `docs/screenshots/`.
