# Performance et budgets mesurés

Mesures reproductibles ; à refaire à chaque changement du démarrage ou du routeur.

## Premier lancement Android (émulateur x86_64, API 36, installation neuve)

| Étape | Durée |
|---|---|
| Imports du cœur Python | 3,0 s |
| Démarrage du cœur (catalogue du cache ou de l'instantané embarqué) | 1,9 s |
| **Cœur prêt (journal `[tontolo] cœur prêt en …`)** | **≈ 5 s** |
| Classements (LMArena…) | en arrière-plan, jamais bloquants |

Les « ~150 s » constatés plus tôt venaient de machines chargées (compilation en parallèle, premier
passage ART/dex2oat après installation par-dessus une ancienne version), pas du cœur. Si un
téléphone réel est lent au premier lancement, relever ces deux lignes avec
`adb logcat -d | grep "\[tontolo\]"` et les ajouter ici.

## Appels courts (résumés, briefs, scénarios)

- Course de 3 modèles gratuits au plus ; **mode économie** (Réglages › Personnalisation) : un seul
  à la fois (moins de réseau, de batterie, de quota).
- Les modèles qui répondent vide, hors format ou tardent comptent comme des échecs dans la
  fiabilité locale (`router/scoring.py`) et passent derrière aux appels suivants ; vitesse observée
  conservée.

## Longues discussions

- Rappel d'un fait ancien (`agent/threadmemory.py`) : fenêtre de 600 messages anciens, 2000
  messages au total, **< 0,5 s** et < 6000 caractères (test `test_very_long_threads_stay_fast_and_bounded`).
- Plus loin que la fenêtre, c'est la fiche de compactage du début du fil qui porte les faits.
