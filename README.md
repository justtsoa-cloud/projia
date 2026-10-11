<p align="center">
  <img src="docs/brand/tontolo-icon-512.png" width="128" alt="Logo Tontolo">
</p>

<h1 align="center">Tontolo</h1>

<p align="center">
  <b>Le meilleur modèle d'IA gratuit, automatiquement.</b><br>
  Hub d'IA libre pour Linux et Android : il choisit le meilleur modèle gratuit pour chaque
  demande, bascule tout seul quand un quota est épuisé, puis revient au meilleur.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-Apache--2.0-blue" alt="Licence Apache-2.0"></a>
  <a href="https://github.com/raantss18/tontolo/actions/workflows/ci.yml"><img src="https://github.com/raantss18/tontolo/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/raantss18/tontolo/releases/latest"><img src="https://img.shields.io/github/v/release/raantss18/tontolo" alt="Dernière version"></a>
</p>

---

<p align="center">
  <img src="docs/screenshots/presentation.png" alt="Tontolo sur Android : réponse avec formules, retouche de photo, modèles gratuits" width="760">
</p>

## Ce que fait Tontolo

- **Choix automatique** du meilleur modèle **gratuit** selon la tâche (code, maths,
  rédaction, traduction, vision, recherche…), d'après les classements en ligne
  d'Artificial Analysis et de LMArena.
- **Bascule automatique** sur quota épuisé (429, quota journalier, erreur fournisseur), **sans
  perdre l'historique**, puis **retour** au meilleur modèle dès qu'il est disponible.
- **Gratuit d'abord** : vos comptes payants ne servent que si vous l'autorisez, avec plafond.
- **Agentique** : recherche web sourcée, lecture de pages, calculatrice, client **MCP**.
- **Multimodal** : images, transcription, synthèse vocale (voix locale toujours disponible),
  vidéo « au mieux ».
- **Toujours à jour** : le catalogue se met à jour à chaque utilisation (nouveaux modèles
  gratuits, modèles retirés, changements de quotas) et l'application se met à jour toute
  seule depuis les releases GitHub (fichiers vérifiés par SHA-256).
- **Fonctionne sans clé** : plus de 30 modèles gratuits sans inscription (Pollinations,
  Kilo Code, LLM7, OVHcloud) ; ajoutez vos clés gratuites (OpenRouter, Groq, Gemini,
  Mistral, NVIDIA…) pour en débloquer davantage.
- **Retouche de photo fidèle** (lumière, contraste, couleurs, noir et blanc, vintage, style
  professionnel…) faite **sur l'appareil**, sans changer la personne ni la composition.
- **Mémoire locale** qui se compacte toute seule, **instructions personnalisées**,
  régénérer, modifier et renvoyer, épingler, exporter en Markdown, raccourcis « / »,
  lecture à voix haute avec arrêt.
- **Sécurisé** : serveur local protégé (jeton, CSRF, DNS rebinding), anti-SSRF, clés
  épinglées à leur fournisseur, outils sensibles soumis à confirmation.
- **Compatible OpenAI** : n'importe quel client OpenAI peut pointer sur Tontolo.

Aucune liste de modèles, aucun classement et aucun quota n'est codé en dur : tout vient des
plateformes en ligne.

## Installation

### Android (7.0 à 16)
Téléchargez l'APK de votre appareil depuis la
[dernière release](https://github.com/raantss18/tontolo/releases/latest), puis ouvrez-le :

| Fichier | Appareils |
|---|---|
| `arm64-v8a` | **Presque tous les téléphones et tablettes depuis 2016** (ARMv8, 64 bits) — le bon choix en cas de doute |
| `armeabi-v7a` | Appareils anciens ou d'entrée de gamme (ARM 32 bits) |
| `x86_64` | Émulateurs, Chromebooks, Android x86 (Intel/AMD) |

> **Message « Google Play Protect : analyse recommandée » ?** Il apparaît pour toute application
> installée hors du Play Store que Google ne connaît pas encore ; ce n'est pas une détection de
> virus. Touchez **Analyser l'application** : l'APK est envoyé à Google pour vérification, puis
> l'installation continue. Tous les APK sont signés avec la même clé et leur empreinte SHA-256
> figure dans `SHA256SUMS` de chaque release ; le code est public.

### Linux (application)
```bash
chmod +x Tontolo-*-x86_64.AppImage
./Tontolo-*-x86_64.AppImage
```

### Linux (CLI et serveur)
```bash
pip install "tontolo[linux] @ https://github.com/raantss18/tontolo/releases/latest/download/tontolo-0.2.8-py3-none-any.whl"
tontolo catalog list --free --category code
tontolo chat "Explique-moi les intégrales"
tontolo serve            # API compatible OpenAI sur http://127.0.0.1:8765/v1
```

Utilisation avec un client OpenAI :

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="inutile-en-local")
r = client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "Bonjour"}])
print(r.model, r.choices[0].message.content)   # modèle réellement utilisé
```

### Mode client-serveur
Lancez `TONTOLO_TOKEN=un-secret tontolo serve --host 0.0.0.0` sur votre machine Linux, puis
dans l'application : **Réglages › Avancé › Serveur distant** (URL + jeton). La
synchronisation de l'historique entre appareils se règle au même endroit.

## Captures

| Réponse avec formules | Retouche fidèle d'une photo | Image gratuite, sans clé |
|:---:|:---:|:---:|
| <img src="docs/screenshots/android-chat.png" width="220"> | <img src="docs/screenshots/android-retouche-photo.png" width="220"> | <img src="docs/screenshots/android-image-gratuite.png" width="220"> |

| Modèles gratuits | Mode sombre | Clés gratuites |
|:---:|:---:|:---:|
| <img src="docs/screenshots/android-modeles-gratuits.png" width="220"> | <img src="docs/screenshots/android-mode-sombre.png" width="220"> | <img src="docs/screenshots/android-reglages.png" width="220"> |

Sur Linux (même application, barre latérale) :

<img src="docs/screenshots/bureau-linux.png" alt="Tontolo sur Linux" width="760">

## Clés gratuites (facultatif)

Dans l'application : **Réglages › Simple › Clés gratuites** (lien direct vers chaque
fournisseur, validation immédiate). En ligne de commande : `tontolo keys set openrouter`,
ou un fichier `.env` (voir `.env.example`). Les clés restent sur votre appareil.

## Performances mesurées (v0.1.0)

Mesures du 2026-10-10 (émulateur Android 16 x86_64, poste Linux KDE). Les budgets sont
vérifiés par la CI : une release qui les dépasse est bloquée.

| Mesure | Valeur mesurée | Budget |
|---|---|---|
| APK arm64-v8a / armeabi-v7a / x86_64 | 24,8 / 23,8 / 25,4 Mo | 30 Mo |
| AppImage Linux x86_64 | 45 Mo | 55 Mo |
| Roue Python | 93 Ko | 150 Ko |
| Interface affichée à froid (Android) | 1,3 à 1,6 s | < 2 s |
| Démarrage du cœur Python embarqué (imports) | 2,6 s, en arrière-plan | non bloquant |
| Sélection du modèle (760 modèles) | < 1 ms | < 20 ms |
| Catalogue depuis le cache | 0,12 s | — |
| Tests automatisés | 88 (cœur) + 4 (interface) | — |
| Android | testé sur 10 (API 29) et 16 (API 36) | ≥ 7 (API 24) |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — fonctionnement et choix techniques
- [Sources](docs/SOURCES.md) — API consultées et dates de vérification
- [Attributions](docs/ATTRIBUTIONS.md) · [Conformité](docs/COMPLIANCE.md)
- [Publier une version](docs/RELEASING.md) · [Maquettes](docs/UI_MOCKUPS.md)
- [Contribuer](CONTRIBUTING.md) · [Sécurité](SECURITY.md) · [Journal](CHANGELOG.md)

## Attributions

Classements : [Artificial Analysis](https://artificialanalysis.ai/) et
[LMArena](https://lmarena.ai/) (CC BY 4.0). Catalogue : [OpenRouter](https://openrouter.ai/).
Fournisseurs gratuits : [awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis).

## Licence

[Apache-2.0](LICENSE) — libre, gratuit, avec licence de brevets explicite.
