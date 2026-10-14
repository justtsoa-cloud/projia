# Vidéos explicatives (mode Apprendre)

« Fais-moi une vidéo qui explique les fractions » → une vidéo animée, avec la voix, en moins
de deux minutes. Gratuit, sur l'appareil, sans que la personne ait à bien formuler sa demande.

## Comment ça marche

```
demande ──► intention ──► demande COMPLÉTÉE ──► scénario (JSON) ──► validation ──► lecteur animé (app)
 (naïve)    (fr/en/mg)    niveau, durée, plan     écrit par modèles   bornes, LaTeX     └─► MP4 (Manim, Linux)
```

1. **Intention** (`explainer/intent.py`) : en mode Apprendre, toute demande de vidéo devient une
   vidéo explicative (un modèle de vidéo générative ne sait ni écrire une formule ni tenir un
   raisonnement). Hors mode Apprendre : « vidéo explicative », « vidéo pédagogique », « manim »…
   Le sujet peut venir de la discussion (« fais-moi une vidéo de ça »).
2. **Complétion des demandes naïves** : la personne n'a rien à préciser. Tontolo choisit le
   niveau (celui du mode Apprendre), la durée (75 s ; « courte » 45 s ; « détaillée » 120 s ;
   « 2 minutes » respecté, borné à 30–180 s), la langue, et impose le plan : accroche → idée
   centrale → UN exemple chiffré résolu → erreur fréquente → récapitulation. Un sujet trop
   vaste (« les maths ») est réduit à UNE notion centrale. Les choix faits sont **dits** à la
   personne (« J'ai choisi pour vous : … »), jamais une question bloquante.
3. **Scénario** (`explainer/writer.py`) : plusieurs modèles gratuits en course ; le premier dont
   le JSON passe la validation gagne ; une réparation ; sinon repli sans modèle tiré de
   l'explication déjà donnée dans la discussion.
4. **Validation** (`explainer/storyboard.py`) : au plus 8 scènes de 7 types (titre, puces,
   équation, étapes, courbe, barres, récapitulation), textes courts, LaTeX filtré, courbes
   calculées par le cœur avec un évaluateur à liste blanche (jamais `eval`).
5. **Lecteur** (`app/lib/ui/explainer_player.dart`) : joue le scénario (Android et Linux, hors
   ligne) : animations, formules, courbes, narration par la voix du système, pause, scène
   suivante. Le bloc ```` ```explainer ```` reste dans la discussion (revoir, partager).
6. **MP4 (facultatif)** (`explainer/manim_render.py`) : sur un Linux qui a Manim et ffmpeg
   (application bureau, ou serveur personnel auquel le téléphone se connecte), le bouton
   « Exporter en vidéo MP4 » produit une vidéo sous-titrée (480p). `GET /tontolo/explainer/capabilities`
   dit ce qui est possible ; sans Manim le bouton n'apparaît pas.

## Sécurité : pas de code venu d'un modèle

Le script Manim est **toujours le même gabarit fixe** ; le scénario validé lui est transmis en
base64 (`DATA = json.loads(base64…)`) : aucun texte libre ne se retrouve dans le code. Le rendu
tourne dans un dossier temporaire, avec limites (temps 5 min, fichiers, descripteurs), sous
bubblewrap sans réseau, dossier personnel et `/run` masqués, quand il est installé. Les formules
sont limitées à un jeu de caractères sûr, sans commande de lecture, d'écriture ni de définition.

## Installer Manim (facultatif, Linux)

```bash
pip install manim          # ou : uv pip install manim
sudo pacman -S ffmpeg texlive-latex texlive-binextra   # Arch ; équivalents ailleurs
export TONTOLO_MANIM_PYTHON=/chemin/vers/python        # si Manim est dans un autre environnement
```

## Limites connues

- Les modèles gratuits sont lents : l'écriture du scénario prend de 1 à 4 minutes quand ils sont
  saturés (la progression est affichée, la réponse continue en arrière-plan).
- Le scénario n'est relu par aucun second modèle : les calculs sont à vérifier (comme tout
  contenu produit par un modèle).
- Le MP4 n'a pas de voix (sous-titres seulement) : la voix est dans le lecteur de l'application.
