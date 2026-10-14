# Campagnes d'affiches

Règle (demandée le 2026-10-14) : **une campagne par jour**, liée aux mises à jour et à l'usage ;
chaque affiche, de version ou de campagne, montre des **prompts courts et usuels** à copier et
**la façon la plus efficace** de s'en servir (niveau + but + format). Fr/en/mg, jamais de prénom
ni de donnée personnelle, pas d'orange, pas d'émoji, QR code vers la dernière version.

## Produire une campagne

1. Créer `press/campaigns/AAAA-MM-JJ/campaign.json` (voir celle du 2026-10-14) : par affiche
   `id`, et par langue `kicker`, `title`, `sub`, `prompts` (3 prompts, une ou deux lignes),
   `tip` (2 lignes), `caption` (texte pour les réseaux, avec le lien).
2. `python3 press/posters/build_campaign.py AAAA-MM-JJ` → PNG 1080 × 1440 + `captions.md`.
3. Vérifier à l'œil (le malgache est le plus long) ; les termes malgaches nouveaux vont dans
   `docs/A_FAIRE_UTILISATEUR.md` pour validation.

## Idées de campagnes (rotation)

- La nouveauté du jour (vidéo, image, voix, mémoire, économie…) avec ses prompts.
- Un cas d'usage : devoirs, résumé de PDF, traduction, lettre, mind map, quiz, révision.
- Une astuce de formulation (niveau + but + format), un avant/après.
- Confiance : ce qui sort du téléphone (presque rien), gratuit, vos clés, local.
- Un chiffre ou un classement de modèles gratuits du moment.

Pour chaque version, joindre aussi une carte de prompts (même gabarit) à l'affiche du changelog.
