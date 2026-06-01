# Alpaca Paper Account — 5-Minute Setup

We use Alpaca for two things: free historical SPY/QQQ bars (now), and paper trading later. The paper account is **free, no credit card, no commitment**. Live trading is a deliberate, much-later step that we'll gate behind 30+ days of paper validation.

## Step 1 — Create the account (~3 minutes)

1. Go to **<https://alpaca.markets/sign-up>**
2. Pick **"Individual"** account type.
3. Fill in name, email, password. Verify your email.
4. On the dashboard you'll land in **Paper Trading** mode by default (look for the toggle in the top-left — it should say "Paper Trading" with a blue badge).

You don't need to fill out the live-trading application (the long KYC form). Skip it. We're not enabling live for months.

## Step 2 — Get your two API keys (~1 minute)

1. In the left sidebar click **"Home"** (or the Alpaca logo).
2. On the right side of the dashboard find the panel labeled **"API Keys"**. (If you don't see it, click **"Paper Overview"** in the sidebar.)
3. Click **"Generate New Key"** (or "View" if one exists).
4. You'll see two strings:
   - **API Key ID** — starts with `PK...` (about 20 chars)
   - **Secret Key** — longer string (about 40 chars)
5. **Copy both immediately.** The Secret Key is shown ONCE — if you close the dialog without copying, you have to regenerate.

## Step 3 — Paste them into your `.env` file (~1 minute)

In your AlphaFactory folder, find the file **`.env`** (NOT `.env.example`).

If `.env` doesn't exist yet, copy `.env.example` to `.env`:

- File Explorer: right-click `.env.example` → Copy → Paste → rename copy to `.env`
- Or in PowerShell from `alpha_factory/`:  `Copy-Item .env.example .env`

Open `.env` in any text editor (Notepad works). Find these two lines:

```
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
```

Paste your keys after the `=` signs, no quotes, no spaces:

```
ALPACA_API_KEY=PKABCDEFGHIJKLMNOPQR
ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Save the file. Done.

## Step 4 — Pull data, just double-click

Back in File Explorer: `alpha_factory\scripts\pull_data.bat` → double-click.

This downloads SPY + QQQ 5-min bars from 2020-01-01 to today. First run takes 2-5 minutes (a few hundred MB of bars). Subsequent runs only fetch what's new.

When it finishes you'll see a `data/bars/SPY/5Min/` folder with one Parquet file per month.

## Step 5 — Run the first backtest

Double-click `alpha_factory\scripts\run_backtest.bat`.

This runs the Range Mean Reversion strategy against your downloaded SPY data and writes a report at:

```
alpha_factory\reports\range_mean_reversion_SPY_<timestamp>.md
```

Open that file. Paste the headline section (or the file path) into our chat and I'll read it and tell you what we learned.

## Troubleshooting

- **`Missing Alpaca credentials`** → `.env` doesn't have the keys, or the file is named `.env.txt` (Windows sometimes hides extensions). Rename to exactly `.env`.
- **`No bars returned`** → SPY/QQQ should always have bars. Most likely cause: the `--start` date is before your account's data history (Alpaca's free `iex` feed has full SPY history, but if you get this, try `--start 2022-01-01`).
- **`HTTP 401` / `Unauthorized`** → keys are wrong, or you accidentally copied the *live* keys (which start with `AK...`) instead of the paper keys (`PK...`). The script defaults to paper URL, so live keys won't authenticate.
- **`HTTP 429` rate limited** → you're hitting Alpaca too hard. The script retries with backoff; if it persists, wait 60 seconds and re-run.

## Security note

`.env` is in `.gitignore`. It will never be committed to a public repo. Keep the file on your machine and treat the Secret Key like a password — don't paste it into chat, screenshots, or emails. If you ever need to share keys with me for debugging, **regenerate them** in the Alpaca dashboard the moment we're done.
