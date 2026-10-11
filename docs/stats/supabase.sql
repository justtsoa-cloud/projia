-- Statistiques anonymes de Tontolo : à exécuter une fois dans Supabase › SQL Editor.
-- Les applications peuvent seulement AJOUTER des lignes (clé « anon ») ; personne d'autre que
-- vous (tableau de bord / clé service) ne peut les lire, les modifier ou les supprimer.

create table if not exists public.pings (
  id          bigint generated always as identity primary key,
  received_at timestamptz not null default now(),
  install_id  text not null check (install_id ~ '^[0-9a-f]{32}$'),
  app_version text not null check (char_length(app_version) <= 20),
  platform    text not null check (platform in ('android', 'linux', 'windows', 'macos', 'ios')),
  os_version  text not null default '' check (char_length(os_version) <= 30),
  abi         text not null default '' check (char_length(abi) <= 20),
  app_locale  text not null default '' check (char_length(app_locale) <= 5),
  country     text not null default '' check (country ~ '^([A-Z]{2})?$'),
  messages    integer not null default 0 check (messages between 0 and 100000)
);

alter table public.pings enable row level security;

-- Insertion seule pour les applications ; aucune politique SELECT/UPDATE/DELETE pour « anon ».
drop policy if exists "apps can insert pings" on public.pings;
create policy "apps can insert pings" on public.pings
  for insert to anon with check (true);

revoke select, update, delete on public.pings from anon, authenticated;
grant insert on public.pings to anon;

create index if not exists pings_received_at on public.pings (received_at);
create index if not exists pings_install on public.pings (install_id);

-- Vues pratiques (lisibles depuis le tableau de bord uniquement).
create or replace view public.stats_daily as
  select date_trunc('day', received_at)::date as jour,
         count(distinct install_id) as appareils_actifs,
         sum(messages) as messages
  from public.pings group by 1 order by 1 desc;

create or replace view public.stats_versions as
  select app_version, platform, count(distinct install_id) as appareils
  from public.pings where received_at > now() - interval '30 days'
  group by 1, 2 order by 3 desc;

create or replace view public.stats_pays as
  select nullif(country, '') as pays, count(distinct install_id) as appareils
  from public.pings where received_at > now() - interval '30 days'
  group by 1 order by 2 desc;

revoke all on public.stats_daily, public.stats_versions, public.stats_pays from anon, authenticated;
