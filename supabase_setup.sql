-- ============================================================
--  Telegram Welcome Bot - full Supabase setup (safe to re-run)
--  Run in: Supabase Dashboard -> SQL Editor -> New query -> Run
--  This REPLACES the old supabase_schema.sql (everything is included here).
-- ============================================================

-- 1) Everyone the bot has greeted (filled automatically by the bot)
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

-- 2) YOUR EDITABLE TEXT  ->  Table Editor -> bot_settings
--    Edit the 'value' cell of the welcome_text row to change the greeting.
--    Keep {name} where the member's name should appear. *asterisks* = bold.
create table if not exists public.bot_settings (
  key   text primary key,
  value text not null
);

insert into public.bot_settings (key, value) values
(
  'welcome_text',
  E'\U0001F44B *Welcome to our community, {name}!*\n\nTo get started, please:\n\n1\uFE0F\u20E3 Read the pinned rules\n2\uFE0F\u20E3 Introduce yourself\n3\uFE0F\u20E3 Check out our resources'
)
on conflict (key) do nothing;

-- 3) YOUR EDITABLE BUTTONS  ->  Table Editor -> buttons
--    One row per button. Add a row = new button, delete a row = button gone.
--    sort_order decides the order (1 shows first).
create table if not exists public.buttons (
  id         bigint generated always as identity primary key,
  sort_order int  not null default 1,
  label      text not null,
  url        text not null
);

insert into public.buttons (sort_order, label, url)
select v.* from (values
  (1, E'\U0001F4D6 Read the Rules', 'https://example.com/rules'),
  (2, E'\U0001F4AC Join the Chat',  'https://t.me/yourchat'),
  (3, E'\U0001F310 Our Website',    'https://example.com')
) as v(sort_order, label, url)
where not exists (select 1 from public.buttons);

-- Lock all tables down for the public/anon key.
-- The bot uses the service_role key, which bypasses RLS, so it still works.
alter table public.members      enable row level security;
alter table public.bot_settings enable row level security;
alter table public.buttons      enable row level security;
