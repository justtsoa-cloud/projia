-- Comptes et synchronisation de Tontolo (0.3.0) : à exécuter une fois dans Supabase › SQL Editor
-- (même projet que les statistiques). Chaque utilisateur ne voit et ne modifie QUE ses lignes ;
-- le contenu (« blob ») est chiffré sur l'appareil (AES-256-GCM) : illisible pour l'auteur.

create table if not exists public.sync_items (
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  kind       text not null check (kind in ('meta', 'conv', 'memory', 'keys')),
  item_id    text not null check (char_length(item_id) between 1 and 64),
  updated_at double precision not null,
  deleted    boolean not null default false,
  blob       text not null default '' check (char_length(blob) <= 2000000),
  server_ts  timestamptz not null default now(),
  primary key (user_id, kind, item_id)
);

alter table public.sync_items enable row level security;

drop policy if exists "own rows select" on public.sync_items;
drop policy if exists "own rows insert" on public.sync_items;
drop policy if exists "own rows update" on public.sync_items;
drop policy if exists "own rows delete" on public.sync_items;
create policy "own rows select" on public.sync_items for select to authenticated
  using (user_id = auth.uid());
create policy "own rows insert" on public.sync_items for insert to authenticated
  with check (user_id = auth.uid());
create policy "own rows update" on public.sync_items for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own rows delete" on public.sync_items for delete to authenticated
  using (user_id = auth.uid());

revoke all on public.sync_items from anon;
grant select, insert, update, delete on public.sync_items to authenticated;

create index if not exists sync_items_pull on public.sync_items (user_id, server_ts);

-- Horodatage serveur à chaque écriture (réception incrémentale fiable) et plafond par compte.
create or replace function public.sync_items_touch() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.server_ts := now();
  if tg_op = 'INSERT' and (select count(*) from public.sync_items where user_id = new.user_id) >= 20000 then
    raise exception 'quota de synchronisation atteint (20 000 éléments)';
  end if;
  return new;
end $$;

drop trigger if exists sync_items_touch on public.sync_items;
create trigger sync_items_touch before insert or update on public.sync_items
  for each row execute function public.sync_items_touch();
