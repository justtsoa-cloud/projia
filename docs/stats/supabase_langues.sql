-- Langues et pays des appareils, lisibles sans se tromper (à exécuter dans Supabase › SQL Editor).
--
-- Avant la version 0.6.4, l'application était en français pour tout le monde tant que la langue
-- n'était pas changée à la main : `app_locale = 'fr'` ne veut donc PAS dire « utilisateur
-- francophone ». Et `country` est la région de la langue du téléphone (« Français (France) » →
-- FR), jamais une position : beaucoup de téléphones à Madagascar sont réglés ainsi.
-- À partir de la 0.6.4, la langue suit celle du téléphone (fr, en, mg ; sinon anglais) et se
-- confirme à l'accueil : la colonne `langue_fiable` sépare les deux périodes.

create or replace view public.stats_langues as
  with derniers as (
    select distinct on (install_id) install_id, app_locale, country, app_version
    from public.pings
    where received_at > now() - interval '30 days'
    order by install_id, received_at desc
  )
  select app_locale as langue,
         nullif(country, '') as region_de_la_langue_du_telephone,
         (string_to_array(split_part(app_version, '+', 1), '.')::int[] >= array[0, 6, 4]) as langue_fiable,
         count(*) as appareils
  from derniers
  group by 1, 2, 3
  order by 4 desc;

revoke all on public.stats_langues from anon, authenticated;
