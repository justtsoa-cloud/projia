# Performance et budgets mesurés

Mesures reproductibles ; à refaire à chaque changement du démarrage ou du routeur.

## Premier lancement Android (émulateur x86_64, API 36, installation neuve)

| Étape | Durée |
|---|---|
| Imports du cœur Python | 3,0 s |
| Démarrage du cœur (catalogue du cache ou de l'instantané embarqué) | 1,9 s |
| **Cœur prêt (journal `[projia] cœur prêt en …`)** | **≈ 5 s** |
| Classements (LMArena…) | en arrière-plan, jamais bloquants |

Les « ~150 s » constatés plus tôt venaient de machines chargées (compilation en parallèle, premier
passage ART/dex2oat après installation par-dessus une ancienne version), pas du cœur. Si un
téléphone réel est lent au premier lancement, relever ces deux lignes avec
`adb logcat -d | grep "\[projia\]"` et les ajouter ici.

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

## Vitesse des réponses (P1, 2026-10-16)

Banc : `core/bench/speed_bench.py` (15 questions fixes fr/en/mg, vrais modèles gratuits ; mesure
préparation, premier mot, durée jusqu'à la réponse complète, justesse). Comparaison :
`uv run python -m bench.speed_bench --compare base2 hedge2` (`PROJIA_NO_HEDGE=1` pour la référence).

| | Référence (sans course) | Course couverte |
|---|---|---|
| Premier mot, médiane | 0,89 s | 1,3 s (bruit) |
| **Premier mot, p90 (pire cas)** | **8,99 s** | **4,42 s (−51 %)** |
| Réponse complète, médiane / p90 | 4,6 s / 14,8 s | 6,3 s / 15,4 s |
| Réponses justes | 14/15 | 13/15 (un contrôle fragile, voir ci-dessous) |

Honnêteté : les modèles gratuits varient beaucoup d'un passage à l'autre (même question : 1 s ou
34 s selon l'heure). Sur 15 questions, la médiane bouge de ±30 % sans changement de code ; seul le
pire cas est stable : la course couverte (`router/hedge.py`) coupe les attentes de 20 à 90 s
(délai d'abandon d'un modèle muet) à ~4 s. Les différences de justesse portent sur des contrôles
de texte fragiles (« 3x² » écrit autrement), pas sur des erreurs de fond ; le banc tolère une
différence d'une réponse et refuse deux.

Mesures conservées dans l'événement `done` (`timing` : prep_s, ttft_s, total_s, attempts).
