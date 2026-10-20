<p align="center">
  <img src="docs/brand/projia-icon-512.png" width="120" alt="Logo Projia">
</p>

<h1 align="center">Projia</h1>

<p align="center">
  <b>Une seule app. Les meilleures IA gratuites.</b><br>
  Projia choisit pour vous le meilleur modèle d'IA gratuit selon ce que vous demandez,<br>
  et en change tout seul quand l'un est saturé. Gratuit, privé, open source.
</p>

<p align="center">
  <a href="https://github.com/justtsoa-cloud/projia/releases/latest"><b>📲 Télécharger pour Android</b></a> ·
  <a href="https://github.com/justtsoa-cloud/projia/releases/latest"><b>🐧 Télécharger pour Linux</b></a> ·
  <a href="#in-english">English</a> ·
  <a href="#aminny-teny-malagasy">Malagasy</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-Apache--2.0-blue" alt="Licence Apache-2.0"></a>
  <a href="https://github.com/justtsoa-cloud/projia/actions/workflows/ci.yml"><img src="https://github.com/justtsoa-cloud/projia/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/justtsoa-cloud/projia/releases/latest"><img src="https://img.shields.io/github/v/release/justtsoa-cloud/projia" alt="Dernière version"></a>
  <img src="https://img.shields.io/badge/prix-0%20%E2%82%AC-67e5be" alt="Gratuit">
  <img src="https://img.shields.io/badge/langues-fr%20%C2%B7%20en%20%C2%B7%20mg-8a7dff" alt="Français, anglais, malgache">
</p>

<p align="center">
  <img src="docs/brand/projia-affiche.png" alt="Projia : apprendre, produire, garder la main" width="560">
</p>

---

## Pourquoi Projia ?

Les IA gratuites sont nombreuses, mais chacune a ses forces, ses quotas et ses pannes. **Projia
les réunit dans une seule application** : il lit votre demande, choisit le modèle gratuit le
mieux classé pour cette tâche (d'après les classements publics d'Artificial Analysis et de
LMArena), et s'il est saturé, passe au suivant **sans perdre le fil**, puis revient au meilleur.

| | |
|:---:|---|
| **773** | modèles référencés, dont **147 gratuits** chez **20 fournisseurs** |
| **45** | modèles utilisables **sans aucune inscription**, dès l'installation |
| **0 €** | ni abonnement, ni publicité, ni compte obligatoire |
| **3** | langues : français, anglais, malgache |
| **100 %** | du code ouvert (Apache-2.0) : auditable, modifiable, auto-hébergeable |

<sub>Chiffres du catalogue au 13 octobre 2026 : il se met à jour tout seul à chaque utilisation.</sub>

## Pour qui ?

### 🎓 Le grand public, les élèves et les étudiants
- **Mode Apprendre** : un tuteur qui guide pas à pas selon votre niveau, sans faire le travail
  à votre place, avec indices et correction d'exercice en photo.
- **Votre cours devient un quiz interactif** ou des fiches de révision : joignez le PDF,
  demandez « crée un quiz de 5 questions ».
- **Vos vidéos comprises** : Projia écoute le son et regarde les images (tableau,
  diapositives, formules), même dans une vidéo muette.
- Recherche web sourcée, images générées gratuitement, retouche fidèle de vos photos, lecture
  à voix haute, dictée.

### 💼 Les professionnels
- **Des documents prêts à envoyer** : Word, PDF, PowerPoint, Excel, présentations Beamer,
  cartes mentales, schémas, graphiques. Chaque fichier est **relu par un second modèle**
  d'une autre famille avant livraison.
- **Toutes vos pièces jointes** : PDF, Office, epub, archives zip, code, sons, vidéos. Les
  longs documents (un livre de 300 pages) sont résumés en fiche compacte sur l'appareil.
- **Des questions à choix** quand la demande est floue (public, longueur, ton), comme un
  collègue qui précise avant de se lancer.
- **Plusieurs modèles sur une même tâche** : « écris le code ; explique-le ; traduis » est
  découpé et confié en parallèle, puis réuni.
- Export des discussions en **PDF** ou Markdown, épinglage, dossiers, mémoire locale.

### 🏢 Les entreprises et les équipes techniques
- **Vos clés, vos données** : les requêtes partent **directement** de l'appareil vers les
  fournisseurs que vous choisissez. Aucun serveur intermédiaire, aucune collecte.
- **API compatible OpenAI** (`model="auto"`) : vos outils existants profitent du routage
  automatique sans changer une ligne de logique.
- **Serveur Linux auto-hébergé** avec jeton, pour toute une équipe sur le réseau local.
- **Modèles locaux** (Ollama, llama.cpp) utilisés automatiquement quand le réseau tombe.
- **Fournisseurs personnalisés**, listes d'exclusion, enchaînements de modèles par type de
  tâche, plafond de dépenses si vous autorisez des modèles payants.
- **Sécurité** : stockage chiffré des clés, protections CSRF, SSRF et DNS rebinding, outils
  sensibles soumis à confirmation, serveurs MCP locaux isolés (bubblewrap), audit documenté
  ([docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md)), métriques locales au format Prometheus.

## Aperçu

| Votre cours en quiz | Une vidéo comprise | Préciser avant d'écrire | Fichier relu et livré |
|:---:|:---:|:---:|:---:|
| <img src="docs/screenshots/android-quiz.png" width="190"> | <img src="docs/screenshots/android-video.png" width="190"> | <img src="docs/screenshots/android-questions.png" width="190"> | <img src="docs/screenshots/android-fichier.png" width="190"> |

| Formules et code | Retouche fidèle | Image gratuite, sans clé | Modèles gratuits |
|:---:|:---:|:---:|:---:|
| <img src="docs/screenshots/android-chat.png" width="190"> | <img src="docs/screenshots/android-retouche-photo.png" width="190"> | <img src="docs/screenshots/android-image-gratuite.png" width="190"> | <img src="docs/screenshots/android-modeles-gratuits.png" width="190"> |

Sur Linux, la même application avec une barre latérale :

<img src="docs/screenshots/bureau-linux.png" alt="Projia sur Linux" width="760">

## Comment ça marche

1. **Vous écrivez** (ou dictez, ou joignez un fichier).
2. **Projia classe la demande** (code, maths, rédaction, traduction, vision, recherche…) et
   choisit le meilleur modèle gratuit disponible pour ce type de tâche.
3. **Si le modèle tarde ou atteint son quota**, il bascule sur le suivant en gardant toute la
   conversation, puis revient au meilleur dès qu'il est libre.
4. **Vous voyez qui répond** : le nom du modèle s'affiche sous chaque réponse, et « Pourquoi
   ce modèle ? » explique le choix. Vos 👍 et 👎 améliorent les choix suivants.

Aucune liste de modèles, aucun classement ni quota n'est codé en dur : tout vient des
plateformes en ligne, et un catalogue de secours embarqué permet de démarrer même sans Internet.

## Installation en une minute

### Android (7.0 à 16)
Téléchargez l'APK depuis la [dernière version](https://github.com/justtsoa-cloud/projia/releases/latest)
et ouvrez-le. L'application se met ensuite à jour toute seule.

| Fichier | Appareils |
|---|---|
| `arm64-v8a` | **Presque tous les téléphones et tablettes depuis 2016** : le bon choix en cas de doute |
| `armeabi-v7a` | Appareils anciens ou d'entrée de gamme (ARM 32 bits) |
| `x86_64` | Émulateurs, Chromebooks, Android x86 |

> **« Google Play Protect : analyse recommandée » ?** Ce message apparaît pour toute application
> installée hors du Play Store que Google ne connaît pas encore ; ce n'est pas une détection de
> virus. Touchez **Analyser l'application**, puis l'installation continue. Tous les APK sont
> signés avec la même clé et leurs empreintes figurent dans `SHA256SUMS` ; le code est public.

### Linux (application)
```bash
chmod +x Projia-*-x86_64.AppImage
./Projia-*-x86_64.AppImage
```

### Linux (ligne de commande et serveur)
```bash
pip install "projia[linux] @ https://github.com/justtsoa-cloud/projia/releases/download/v0.6.1/projia-0.6.1-py3-none-any.whl"
projia catalog list --free --category code
projia chat "Explique-moi les intégrales"
projia serve            # API compatible OpenAI sur http://127.0.0.1:8765/v1
```

Avec n'importe quel client OpenAI :

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="inutile-en-local")
r = client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "Bonjour"}])
print(r.model, r.choices[0].message.content)   # modèle réellement utilisé
```

Référence complète de l'API : [docs/API.md](docs/API.md).

### Pour une équipe (client-serveur)
Lancez `PROJIA_TOKEN=un-secret projia serve --host 0.0.0.0` sur une machine Linux, puis dans
chaque application : **Réglages › Avancé › Serveur distant** (adresse + jeton).

### Modèles locaux, sans Internet
Si [Ollama](https://ollama.com) (port 11434) ou `llama-server` de
[llama.cpp](https://github.com/ggml-org/llama.cpp) (port 8080) tourne sur l'appareil, Projia le
détecte et s'en sert en dernier recours, et tout de suite quand le réseau est coupé. La
détection n'interroge que `127.0.0.1`.

```bash
ollama pull llama3.2:3b
```

## Clés gratuites (facultatif)

Projia fonctionne sans aucune clé. Pour débloquer davantage de modèles, ajoutez vos clés
gratuites (OpenRouter, Groq, Gemini, Mistral, NVIDIA…) dans **Réglages › Simple › Clés
gratuites** : lien direct vers chaque fournisseur, validation immédiate. Les clés restent sur
votre appareil, dans le stockage sécurisé du système.

## Qualité vérifiée

Chaque version est bloquée si un contrôle échoue : analyse statique, typage, plus de 400 tests
du cœur et 68 tests de l'interface, garde-fou de performance (30 utilisateurs simultanés, fil
de 1 500 messages), budgets de taille.

| Mesure (v0.6.1) | Valeur |
|---|---|
| APK arm64-v8a / armeabi-v7a / x86_64 | 26 / 25 / 26 Mo (budget 30 Mo) |
| AppImage Linux x86_64 | 45 Mo (budget 55 Mo) |
| Cœur Python | moins de 300 Ko |
| Sélection du modèle parmi tout le catalogue | moins d'une milliseconde |
| Android testé | 10 (API 29) et 16 (API 36), minimum 7.0 |

## In English

**One app. The best free AI models.** Projia picks the best free AI model for each request
(studies, code, writing, translation, vision, search…) according to public rankings, and
switches by itself when one is busy, without losing the conversation.

- **Everyone**: Learn mode with a step-by-step tutor, your course turned into an interactive
  quiz, videos understood (sound and images), free image generation, faithful photo retouching.
- **Professionals**: ready-to-send Word, PDF, PowerPoint, Excel, Beamer and mind maps, checked
  by a second model; every kind of attachment; PDF export of chats.
- **Businesses**: your own keys and no middleman, OpenAI-compatible API (`model="auto"`),
  self-hosted Linux server, local models when offline, open source under Apache-2.0.

Free, no subscription, no ads. Android and Linux:
[download the latest release](https://github.com/justtsoa-cloud/projia/releases/latest).

## Amin'ny teny malagasy

**App iray monja. Ireo IA maimaim-poana tsara indrindra.** Mifidy ny modely IA maimaim-poana
tsara indrindra isaky ny fangatahana i Projia (lesona, kaody, fanoratana, fandikan-teny,
sary…), ary miova ho azy raha feno ny iray, nefa tsy very ny resaka.

- **Ho an'ny rehetra**: mpampianatra dingana tsirairay, lasa quiz mifandray ny lesonao, azo
  ny horonan-tsarinao (feo sy sary).
- **Ho an'ny matihanina**: Word, PDF, PowerPoint, takelaka ary sarintsaina vonona halefa,
  jeren'ny modely faharoa.
- **Ho an'ny orinasa**: ny fanalahidinao, tsy misy mpanelanelana, API mifanaraka amin'ny
  OpenAI, mpizara Linux, kaody misokatra.

Maimaim-poana, tsy misy famandrihana, tsy misy doka. Android sy Linux:
[ampidino ny dikan-teny farany](https://github.com/justtsoa-cloud/projia/releases/latest).

## Documentation

- [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Sources](docs/SOURCES.md)
- [Sécurité](SECURITY.md) · [Audit](docs/SECURITY_AUDIT.md) · [Conformité](docs/COMPLIANCE.md)
- [Comptes et synchronisation](docs/ACCOUNTS.md) · [Boutiques](docs/DISTRIBUTION.md)
- [Publier une version](docs/RELEASING.md) · [Contribuer](CONTRIBUTING.md) · [Journal](CHANGELOG.md)

## Auteur

**RANIRIAMANJAKA Antsa**, conception et développement
- GitHub : [github.com/raantss18](https://github.com/raantss18)
- E-mail : [antsa.raniriamanjaka@univ-antananarivo.mg](mailto:antsa.raniriamanjaka@univ-antananarivo.mg)
- Téléphone / WhatsApp : [+261 33 43 838 82](https://wa.me/261334383882)

## Attributions

Classements : [Artificial Analysis](https://artificialanalysis.ai/) et
[LMArena](https://lmarena.ai/) (CC BY 4.0). Catalogue : [OpenRouter](https://openrouter.ai/).
Fournisseurs gratuits : [awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis).

## Licence

[Apache-2.0](LICENSE) : libre, gratuit, avec licence de brevets explicite.
