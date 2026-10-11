# Comptes et synchronisation (0.3.0)

Facultatifs. Un compte (Google ou GitHub) permet de retrouver ses **discussions** (avec
dossiers, épingles et mode Apprendre), ses **mémoires** et ses **clés d'API** sur tous ses
appareils. Sans compte, Tontolo fonctionne exactement comme avant.

## Ce que voit le serveur : rien de lisible
- Le compte donne l'**accès** (Supabase Auth, flux OAuth PKCE). La **lecture** exige la
  *phrase secrète de synchronisation*, choisie par l'utilisateur et jamais transmise.
- Clé : PBKDF2-HMAC-SHA256 (310 000 itérations, sel aléatoire par compte), 256 bits.
  Chiffrement : AES-256-GCM, nonce aléatoire par élément, données associées `type|identifiant`.
- La base (`sync_items`) ne contient que des blobs chiffrés, l'identifiant de l'élément et des
  horodatages. Les règles RLS limitent chaque ligne à son propriétaire.

## Fonctionnement
- Une conversation est synchronisée **entière** ; la version la plus récente l'emporte
  (suppressions, régénérations et modifications se propagent sans doublons). Limite : si la
  même discussion est modifiée sur deux appareils hors ligne, la plus ancienne modification
  est perdue ; une horloge d'appareil très décalée peut fausser l'ordre.
- Mémoires : ajouts et suppressions propagés (identifiant = empreinte du texte).
- Clés d'API : ajoutées sur les autres appareils si absentes ; une clé locale différente
  n'est jamais écrasée.
- Images de plus de 500 Ko et conversations de plus de ≈ 1,9 Mo chiffrées : non envoyées.
- Phrase oubliée : données en ligne illisibles (les données des appareils restent) ;
  « Supprimer mes données en ligne » permet de repartir de zéro.
- Déconnexion : jetons et clé effacés de l'appareil ; les données locales restent.
- Suppression complète du compte : sur demande à l'auteur (voir README).

## Mise en service (propriétaire du projet Supabase)
1. **SQL** : exécuter `docs/accounts/supabase_sync.sql` dans *SQL Editor*.
2. **URL de retour** : *Authentication › URL Configuration › Redirect URLs*, ajouter
   `http://localhost:43823/` (Linux et anciennes versions Android), ainsi que
   `io.github.raantss18.tontolo://login-callback/` (Android à partir de la 0.4.7).
   Conserver les deux URL exactes, sans wildcard.
3. **Google** : console.cloud.google.com › *APIs & Services › Credentials* › *Create
   credentials › OAuth client ID* (type *Web application*), *Authorized redirect URI* :
   `https://<projet>.supabase.co/auth/v1/callback`. Puis Supabase › *Authentication ›
   Providers › Google* : activer, coller *Client ID* et *Client secret*.
   (Écran de consentement OAuth : nom « Tontolo », e-mail d'assistance, publier l'app.)
4. **GitHub** : github.com › *Settings › Developer settings › OAuth Apps › New OAuth App*,
   *Authorization callback URL* : `https://<projet>.supabase.co/auth/v1/callback`. Puis
   Supabase › *Providers › GitHub* : activer, coller *Client ID* et *Client secret*.
5. Les applications publiées utilisent déjà l'adresse et la clé publique du projet
   (variables GitHub `STATS_URL` / `STATS_ANON_KEY`) : aucune autre configuration.

Tant que les fournisseurs ne sont pas activés, le bouton de connexion affiche « Cette
méthode de connexion n'est pas encore activée ».
