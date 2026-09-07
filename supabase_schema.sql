-- Run this once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run

create table if not exists public.members (
  id          bigint generated always as identity primary key,
  telegram_id bigint not null,
  username    text,
  first_name  text,
  chat_id     bigint not null,
  source      text not null check (source in ('start', 'group_join')),
  created_at  timestamptz not null default now(),
  unique (telegram_id, chat_id)  -- one row per person per chat (re-joins just update)
);

-- Lock the table down for the public/anon key.
-- The bot uses the service_role key, which bypasses RLS, so it still works.
alter table public.members enable row level security;
