# Statistiques d'utilisation (Supabase)

Tontolo peut envoyer, **une fois par jour au plus**, des statistiques **anonymes** à la base
de l'auteur. Activées par défaut, annoncées dans l'accueil et désactivables dans
*Réglages › Statistiques anonymes* (le bouton « Voir ce qui est envoyé » montre les données
exactes).

| Donnée | Exemple | Pourquoi |
|---|---|---|
| `install_id` | identifiant aléatoire de 32 caractères, créé sur l'appareil | compter les appareils sans les identifier |
| `app_version`, `platform`, `os_version`, `abi` | `0.2.10`, `android`, `Android 14`, `arm64` | savoir quelles versions et quels appareils suivre |
| `app_locale`, `country` | `mg`, `MG` (langue de l'application ; région de la langue du téléphone, **jamais une position**) | prioriser les langues |
| `messages` | `12` (nombre de messages depuis le dernier envoi) | mesurer l'usage |

Jamais envoyés : messages, images, voix, clés, nom, adresse IP stockée par Tontolo, contacts,
modèle exact de l'appareil.

### Lire la langue et le pays sans se tromper (corrigé en 0.6.4)

- **Avant la 0.6.4**, l'application était en français pour tout le monde tant qu'on n'avait pas
  changé la langue à la main : `app_locale = 'fr'` surestimait donc fortement le français. Depuis
  la 0.6.4, la langue suit celle du téléphone (fr, en, mg ; sinon anglais) et se confirme à
  l'accueil.
- **`country` n'est pas une localisation** : c'est la région de la langue du téléphone (« Français
  (France) » donne FR). Un téléphone à Madagascar réglé ainsi apparaît en FR.
- La vue `stats_langues` ([`docs/stats/supabase_langues.sql`](stats/supabase_langues.sql)) sépare
  les appareils à langue fiable (≥ 0.6.4) des autres. Pour une vraie localisation, il faudrait
  collecter davantage (fuseau horaire…) ; ce n'est pas fait, par choix de confidentialité.

## Notes 👍 / 👎 (depuis 0.5.8)

Avec le même accord (*Statistiques anonymes*), chaque note donnée à une réponse est partagée,
groupée avec l'envoi quotidien :

| Donnée | Exemple | Pourquoi |
|---|---|---|
| `answer_id` | identifiant aléatoire de la réponse (32 caractères) | une seule note par réponse et par appareil |
| `model`, `category` | `groq:llama-3.3-70b`, `code` | savoir quel modèle réussit quel type de demande |
| `rating`, `reason` | `-1`, `too_long` | récompenser ou pénaliser le modèle |
| `cached` | `false` | distinguer une réponse réutilisée |

Jamais envoyés : la question, la réponse, ni aucun texte.

**Effet** : sur l'appareil, une note agit tout de suite (bonus ou malus borné du modèle pour ce
type de demande ; une réponse 👎 n'est plus réutilisée). Chaque jour, l'application lit la
fonction `model_scores()` : le solde des **appareils** (pas des votes) par modèle et type de
demande, à partir de 5 appareils. Ce score collectif pèse moins que les notes de l'appareil.

## Mise en place (une seule fois, par le propriétaire)

1. Créez un projet gratuit sur [supabase.com](https://supabase.com).
2. *SQL Editor* : collez et exécutez [`docs/stats/supabase.sql`](stats/supabase.sql), puis
   [`docs/stats/supabase_ratings.sql`](stats/supabase_ratings.sql) (notes, depuis 0.5.8).
3. *Project Settings › API* : copiez l'**URL du projet** et la clé **anon public**
   (clé publique par conception : elle ne permet que d'ajouter des lignes).
4. Sur GitHub, *Settings › Secrets and variables › Actions › Variables* du dépôt, créez :
   - `STATS_URL` = l'URL du projet (`https://xxxx.supabase.co`)
   - `STATS_ANON_KEY` = la clé anon public
5. Publiez une nouvelle version : les applications construites ensuite enverront leurs
   statistiques. Sans ces variables, l'envoi reste inactif.

## Consulter les chiffres

Dans Supabase › *Table editor* ou *SQL Editor* : vues `stats_daily` (appareils actifs et
messages par jour), `stats_versions` (versions et plateformes sur 30 jours), `stats_pays`,
`stats_ratings` (👍 / 👎 par modèle et type de demande sur 30 jours, raison la plus fréquente).
