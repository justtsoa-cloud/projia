-- Migration additive : les anciennes tables restent intactes pour les anciennes versions.
-- Les nouvelles versions envoient exactement langue, pays approximatif et version.
begin;
create table if not exists public.pings_minimal (
  id bigint generated always as identity primary key,
  received_at timestamptz not null default now(),
  app_version text not null check (char_length(app_version) between 1 and 20),
  app_locale text not null check (app_locale in ('fr', 'en', 'mg')),
  country text not null check (country ~ '^([A-Z]{2})?$')
);
alter table public.pings_minimal enable row level security;
revoke all on public.pings_minimal from anon, authenticated;
grant insert (app_version, app_locale, country) on public.pings_minimal to anon;
drop policy if exists "apps insert minimal pings" on public.pings_minimal;
create policy "apps insert minimal pings" on public.pings_minimal
  for insert to anon with check (true);
create index if not exists pings_minimal_received_at on public.pings_minimal (received_at);
commit;
