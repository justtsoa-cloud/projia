# Contribuer à Projia

Merci ! Les contributions sont bienvenues (code, traductions, documentation, tests).

## Mise en place

```bash
cd core && uv venv && uv pip install -e ".[dev,linux]"
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/mypy
cd ../app && flutter pub get && flutter analyze && flutter test
```

## Règles

- Commentaires et documentation **en français**, identifiants en anglais.
- Commits [Conventional Commits](https://www.conventionalcommits.org/fr/) (`feat:`, `fix:`…).
- **Aucune liste de modèles, classement ou quota codé en dur** : tout vient des sources en ligne.
- Chaque ajout doit justifier son poids (taille, mémoire, démarrage, batterie).
- Tests obligatoires pour le routeur, les quotas et la bascule (fournisseurs simulés).
- Traductions : `app/lib/l10n/strings.dart` (fr, en, mg).

En contribuant, vous acceptez que votre contribution soit publiée sous licence Apache-2.0.
