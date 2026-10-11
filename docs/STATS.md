# Statistiques d'utilisation (Supabase)

Tontolo peut envoyer, **une fois par jour au plus**, des statistiques **anonymes** à la base
de l'auteur. Activées par défaut, annoncées dans l'accueil et désactivables dans
*Réglages › Statistiques anonymes* (le bouton « Voir ce qui est envoyé » montre les données
exactes).

| Donnée | Exemple | Pourquoi |
|---|---|---|
| `install_id` | identifiant aléatoire de 32 caractères, créé sur l'appareil | compter les appareils sans les identifier |
| `app_version`, `platform`, `os_version`, `abi` | `0.2.10`, `android`, `Android 14`, `arm64` | savoir quelles versions et quels appareils suivre |
| `app_locale`, `country` | `mg`, `MG` (pays de la langue du téléphone, pas de géolocalisation) | prioriser les langues |
| `messages` | `12` (nombre de messages depuis le dernier envoi) | mesurer l'usage |

Jamais envoyés : messages, images, voix, clés, nom, adresse IP stockée par Tontolo, contacts,
modèle exact de l'appareil.

## Mise en place (une seule fois, par le propriétaire)

1. Créez un projet gratuit sur [supabase.com](https://supabase.com).
2. *SQL Editor* : collez et exécutez [`docs/stats/supabase.sql`](stats/supabase.sql).
3. *Project Settings › API* : copiez l'**URL du projet** et la clé **anon public**
   (clé publique par conception : elle ne permet que d'ajouter des lignes).
4. Sur GitHub, *Settings › Secrets and variables › Actions › Variables* du dépôt, créez :
   - `STATS_URL` = l'URL du projet (`https://xxxx.supabase.co`)
   - `STATS_ANON_KEY` = la clé anon public
5. Publiez une nouvelle version : les applications construites ensuite enverront leurs
   statistiques. Sans ces variables, l'envoi reste inactif.

## Consulter les chiffres

Dans Supabase › *Table editor* ou *SQL Editor* : vues `stats_daily` (appareils actifs et
messages par jour), `stats_versions` (versions et plateformes sur 30 jours), `stats_pays`.
