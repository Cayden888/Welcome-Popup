# Telegram Welcome Bot

**Pipeline:** GitHub (code) → Supabase (database) → Railway (hosting) → Telegram (bot)

Greets each person by name with tappable buttons, both on `/start` in private chat and when someone joins your group. Every greeted person is saved to a Supabase `members` table so you can see who joined and when.

## ⚠️ Before anything else: regenerate your token

If your bot token has ever been pasted into a chat, screenshot, or commit, treat it as compromised. In Telegram, open **@BotFather → /mybots → your bot → API Token → Revoke** to get a fresh one. The token only ever goes into environment variables — never into the code.

## 1. GitHub

1. Create a new repository (private is fine).
2. Push these files: `bot.py`, `requirements.txt`, `Procfile`, `.gitignore`, `.env.example`, `supabase_schema.sql`, `README.md`.
3. Double-check the repo does **not** contain a real `.env` or any token — `.gitignore` already excludes `.env`.

## 2. Supabase

1. Go to [supabase.com](https://supabase.com), create a project (free tier is fine).
2. Open **SQL Editor → New query**, paste the contents of `supabase_schema.sql`, and click **Run**. This creates the `members` table.
3. Go to **Project Settings → API** and copy two things:
   - the **Project URL** (looks like `https://xxxx.supabase.co`)
   - the **service_role** key (secret — this is your `SUPABASE_KEY`)

## 3. Railway

1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo** and pick your repo.
2. In the service, open the **Variables** tab and add:
   - `BOT_TOKEN` — your fresh token from BotFather
   - `SUPABASE_URL` — the project URL from step 2
   - `SUPABASE_KEY` — the service_role key from step 2
3. The `Procfile` tells Railway to run `python bot.py` as a worker. If it doesn't pick that up automatically, set **Settings → Start Command** to `python bot.py`.
4. Deploy, then open the logs — you should see `Bot is running.`

The bot uses long polling, so it needs no domain, port, or webhook — one always-on Railway worker is all it takes.

## 4. Telegram

1. Open your bot in Telegram and send `/start` — you should get the welcome message with buttons.
2. For group welcomes: add the bot to your group and **make it an admin** (required for it to see joins).
3. Have someone join the group — they get greeted, and a row appears in Supabase under **Table Editor → members**.

## Customizing

Edit `WELCOME_TEXT` and `BUTTONS` near the top of `bot.py`, commit, and push — Railway redeploys automatically on every push to GitHub.

## Running locally (optional)

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your real values
python bot.py
```
