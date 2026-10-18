-- Retours d'expérience (facultatifs, envoyés seulement si l'utilisateur coche « Envoyer »).
-- Insertion seule ; aucune lecture avec la clé publique ; aucun identifiant, aucun texte de
-- discussion. Migration additive : n'efface rien.
begin;
create table if not exists public.feedback (
  id bigint generated always as identity primary key,
  received_at timestamptz not null default now(),
  mood smallint not null check (mood between 1 and 3),
  reasons text[] not null default '{}',
  note text not null default '' check (char_length(note) <= 280),
  rating smallint not null default 0 check (rating between 0 and 5),
  app_version text not null check (char_length(app_version) between 1 and 20),
  app_locale text not null check (app_locale in ('fr', 'en', 'mg'))
);
alter table public.feedback enable row level security;
revoke all on public.feedback from anon, authenticated;
grant insert (mood, reasons, note, rating, app_version, app_locale) on public.feedback to anon;
drop policy if exists "apps insert feedback" on public.feedback;
create policy "apps insert feedback" on public.feedback for insert to anon with check (true);
commit;
