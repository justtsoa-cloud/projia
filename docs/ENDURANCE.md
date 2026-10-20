# Essais d'endurance

Deux familles d'essais. Les **bancs** (`core/bench/b*.py`) mesurent le cœur seul, avec un faux
fournisseur : ils ne dépendent pas des modèles et se relancent à l'identique. Les **essais réels**
(`core/bench/real_e2e.py`) lancent un vrai serveur avec les modèles gratuits : leurs durées
dépendent de la charge des fournisseurs le jour de l'essai.

Résultats bruts (non versionnés) : `core/bench/results/`.

## Bancs (cœur seul)

| Banc | Charge | Résultat |
|---|---|---|
| `b1_long_thread` | fil de 8 000 messages | un tour en 90 à 170 ms, environ 100 Mo de mémoire |
| `b2_many_conversations` | 500 discussions × 30 messages | requêtes < 5 ms, export en 105 ms |
| `b3_concurrency` | 300 utilisateurs × 8 tours, pannes injectées | 0 erreur, fils cohérents, ≈ 3 ms de surcoût par tour |
| `b4_creator_stress` | 30 créations en parallèle, livre de 120 chapitres, zip de 60 fichiers | rapide, aucune erreur |
| `b5_leaks` | 60 terminaux ouverts puis fermés | aucun descripteur ni processus fils restant |
| `tests/test_fuzz_api.py` | entrées hostiles (Unicode invalide, corps malformés, identifiants bizarres) | aucune erreur 500 |

```bash
cd core
uv run python -m bench.b3_concurrency 300 8
uv run python bench/b5_leaks.py
```

## Essais réels (modèles gratuits)

| Essai | Ce qui est vérifié | Résultat |
|---|---|---|
| R2 plan complexe | plan, 4 pays traités, « continuer » livre l'étape suivante | réussi (148 s) |
| R3 longue discussion | 14 tours, prénom et ville retrouvés à la fin | réussi (661 s) |
| R4 chaîne de corrections | 4 corrections successives d'un Word, noms jamais dupliqués | réussi |
| R6 projet de code | zip, fichiers Python qui compilent, tests générés qui passent | réussi (44 s) |
| R7 livre de 21 pages | plan, chapitres en parallèle, PDF compilé | voir ci-dessous |
| R8 agent et outils | recherche web, calculatrice, aucun balisage brut | réussi (28 s) |

```bash
cd core
uv run python -m bench.real_e2e r2_complex_plan r3_long_conversation r4_revision_chain \
  r6_code_project r7_book r8_agent_tools
```

## Ce qui dépend des modèles

- **Discussion, questions, code court** : fiable. Si un modèle échoue, se tait (90 s sans
  premier mot, 60 s de blocage) ou plante, le routeur passe au suivant.
- **Documents de 1 à 15 pages, projets en zip** : fiables. Le titre manquant est toléré, et les
  citations ne sont jamais inventées : celles qui ne sont pas sûres sont marquées (≈).
- **Livres longs** : la durée dépend de la charge des modèles gratuits. Chaque chapitre a son
  délai et deux essais. Un chapitre qui n'arrive pas est remplacé par un chapitre « à refaire ».
  Un chapitre qui ne compile pas après trois corrections est simplifié : le texte est gardé
  sans mise en forme.
- **Vitesse** : les catalogues ne donnent pas la vitesse de la plupart des modèles gratuits.
  Projia mesure la vitesse réelle de chaque modèle et favorise les plus rapides pour les
  échanges simples.

Les bugs trouvés et corrigés (B1 à B14, O1) sont listés dans `TASKS.md`, section « Tests
d'endurance ».
