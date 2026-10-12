-- Notes 👍 / 👎 anonymes de Tontolo (0.5.8) : à exécuter une fois dans Supabase › SQL Editor,
-- après supabase.sql. Aucun texte n'est jamais envoyé : seulement le modèle, le type de
-- demande, la note et une raison courte.
--
-- - Les applications peuvent seulement AJOUTER des notes (clé « anon »), une par appareil et
--   par réponse, 300 par appareil et par jour au plus.
-- - Elles peuvent lire UNIQUEMENT l'agrégat `model_scores()` : par modèle et type de demande,
--   le solde des appareils (et non des votes : un appareil qui vote 50 fois compte une fois),
--   seulement à partir de 5 appareils.

create table if not exists public.ratings (
  id          bigint generated always as identity primary key,
  received_at timestamptz not null default now(),
  install_id  text not null check (install_id ~ '^[0-9a-f]{32}$'),
  answer_id   text not null check (answer_id ~ '^[0-9a-f]{32}$'),
  app_version text not null check (char_length(app_version) <= 20),
  platform    text not null check (platform in ('android', 'linux', 'windows', 'macos', 'ios')),
  app_locale  text not null default '' check (char_length(app_locale) <= 5),
  model       text not null check (char_length(model) <= 200 and model ~ '^[A-Za-z0-9._:/@+-]+$'),
  category    text not null check (category in ('chat', 'code', 'math', 'reasoning', 'writing',
                'translation', 'vision', 'long_context', 'agentic', 'search')),
  rating      smallint not null check (rating in (-1, 1)),
  reason      text not null default '' check (reason in ('', 'inexact', 'off_topic', 'too_long',
                'too_short', 'language', 'other')),
  cached      boolean not null default false,
  unique (install_id, answer_id)
);

alter table public.ratings enable row level security;

drop policy if exists "apps can insert ratings" on public.ratings;
create policy "apps can insert ratings" on public.ratings
  for insert to anon with check (true);

revoke select, update, delete on public.ratings from anon, authenticated;
grant insert on public.ratings to anon;

create index if not exists ratings_received_at on public.ratings (received_at);
create index if not exists ratings_install_day on public.ratings (install_id, received_at);
create index if not exists ratings_model on public.ratings (model, category);

-- Plafond quotidien par appareil (contre le remplissage automatique).
create or replace function public.ratings_daily_cap() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if (select count(*) from public.ratings
      where install_id = new.install_id and received_at > now() - interval '1 day') >= 300 then
    raise exception 'quota quotidien de notes atteint';
  end if;
  return new;
end $$;

drop trigger if exists ratings_daily_cap on public.ratings;
create trigger ratings_daily_cap before insert on public.ratings
  for each row execute function public.ratings_daily_cap();

-- Agrégat lisible par les applications : solde des appareils sur 90 jours, par modèle et type
-- de demande, et tous types confondus (category = '*').
create or replace function public.model_scores()
returns table (model text, category text, devices bigint, score double precision)
language sql stable security definer set search_path = public as $$
  with per_device as (
    select install_id, r.model, r.category, sign(sum(rating)) as s
    from public.ratings r
    where received_at > now() - interval '90 days'
    group by 1, 2, 3
  ), per_device_all as (
    select install_id, r.model, '*'::text as category, sign(sum(rating)) as s
    from public.ratings r
    where received_at > now() - interval '90 days'
    group by 1, 2
  ), merged as (
    select * from per_device union all select * from per_device_all
  )
  select m.model, m.category, count(*) as devices,
         (count(*) filter (where s > 0) - count(*) filter (where s < 0))::double precision
           / count(*) as score
  from merged m where s <> 0
  group by 1, 2
  having count(*) >= 5
$$;

revoke all on function public.model_scores() from public;
grant execute on function public.model_scores() to anon, authenticated;

-- Vue pour le tableau de bord du propriétaire uniquement.
create or replace view public.stats_ratings as
  select model, category,
         count(*) filter (where rating = 1) as pouces_haut,
         count(*) filter (where rating = -1) as pouces_bas,
         count(distinct install_id) as appareils,
         mode() within group (order by nullif(reason, '')) as raison_frequente
  from public.ratings where received_at > now() - interval '30 days'
  group by 1, 2 order by pouces_bas desc, appareils desc;

revoke all on public.stats_ratings from anon, authenticated;
