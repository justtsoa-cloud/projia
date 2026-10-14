# Statistiques minimales

Depuis la phase A après v0.6.5, Tontolo peut envoyer **au plus une tentative par jour**
à Supabase. L'envoi est annoncé à l'accueil et désactivable dans
*Réglages › Statistiques anonymes*. Sans configuration à la compilation, aucun envoi.

La liste blanche est exacte :
- `app_version` : version de l'application ;
- `app_locale` : langue choisie (`fr`, `en`, `mg`) ;
- `country` : région de la langue du téléphone, ou chaîne vide si inconnue.

Le pays n'est **pas une position** : « Français (France) » donne FR, même si le téléphone
est à Madagascar. Aucun GPS, aucune adresse IP collectée par le code de Tontolo.
Comme tout service HTTP, l'hébergeur reçoit nécessairement l'adresse IP de connexion ;
Tontolo ne l'ajoute pas aux statistiques ni ne contrôle les journaux de l'hébergeur.

Ne sont plus envoyés : identifiant d'installation, système, ABI, compteur de messages,
identifiant de réponse, modèle, catégorie, note et raison de la note. Les files de notes
restantes des anciennes versions sont vidées sans envoi. Les 👍/👎 continuent d'améliorer
le choix des modèles **localement**. Aucun texte de discussion, prénom, fichier ou clé
personnelle n'est envoyé aux statistiques. La clé `anon` de Supabase est une clé publique
d'insertion ; ce n'est pas une clé API personnelle de fournisseur.

L'écran « Voir ce qui est envoyé » montre exactement le corps de la requête.
Les tests `app/test/stats_test.dart` inspectent ce corps avec un transport simulé,
injectent de fausses données sensibles dans les anciens champs et vérifient leur absence.
Un échec réseau ne déclenche pas de boucle de tentatives dans la journée.

## Migration côté Supabase

Exécuter `docs/stats/supabase_minimal.sql` dans le SQL Editor du projet existant.
Cette migration additive crée `pings_minimal`, avec insertion seule pour le rôle `anon`.
Les lectures, modifications et suppressions publiques sont interdites. Aucun accès aux
anciennes données n'est modifié. Avant cette migration, les nouveaux envois sont refusés
par le serveur et l'application continue normalement, sans repli vers l'ancien format.

Les variables de compilation restent `STATS_URL` et `STATS_ANON_KEY` dans GitHub Actions.
La nouvelle table ne permet **pas** de compter des appareils uniques, car aucun identifiant
n'est transmis. Le propriétaire peut compter les envois et leur répartition, sans les
présenter comme un nombre exact d'utilisateurs.

## Historique

Jusqu'à v0.6.5, `pings` recevait également un identifiant aléatoire d'installation,
le système et un compteur ; `ratings` recevait des notes anonymisées. Les versions déjà
installées peuvent continuer à utiliser ces tables tant qu'elles ne sont pas mises à jour.
Les scripts SQL historiques sont conservés pour compatibilité et ne décrivent pas le
nouveau format. Leur suppression éventuelle exige une décision séparée du propriétaire.
Avant v0.6.4, la langue française par défaut faussait sa répartition : les vues historiques
`stats_langues` distinguent les versions concernées.
