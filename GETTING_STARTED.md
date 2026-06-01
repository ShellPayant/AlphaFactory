# Getting Started — for the novice operator

Welcome. This guide assumes zero prior Python or trading-engine experience. We are going to:

1. Get your computer ready (one-time, ~10 minutes)
2. Run the existing test suite to prove everything works
3. Decide together which broker/data accounts you'll sign up for, and when

You will NOT be writing any code. Claude writes the code. You read it, ask questions, and approve.

---

## Step 1 — Run the setup script

Open Windows File Explorer and navigate to:

```
AlgoTrading - Claude\AlgoTrading\alpha_factory\scripts\
```

Right-click **`setup.ps1`** → **"Run with PowerShell"**.

A blue terminal window will open and do four things:

1. Install **uv** (a tiny Python package manager from the makers of Ruff)
2. Download Python 3.12 if you don't have it
3. Install all AlphaFactory dependencies (~150 MB, 2-5 min)
4. Run the test suite

### If Windows blocks the script

You may see: *"running scripts is disabled on this system"*. To fix it ONCE:

1. Search the Start Menu for **"PowerShell"**
2. Right-click → **"Run as Administrator"**
3. Paste: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
4. Press Enter, type **Y**, press Enter
5. Close that PowerShell window and try Step 1 again

### What success looks like

At the end you'll see a green box that says **"Setup complete. Tests passed."**

If you see a **yellow box** ("some tests failed") instead, scroll up in the terminal, copy the red error text, and paste it into our chat. Claude will fix it.

---

## Step 2 — Confirm in chat

Once setup is done, just tell Claude:

> "Setup script done, tests green."

(or paste any errors). That's it. You're at the end of Phase 1 — you have a tested, working indicators + regime classifier system on your machine.

---

## Step 3 — From now on, run tests anytime with one click

Double-click **`scripts\run_tests.bat`** any time you want to re-run the test suite. No PowerShell, no commands.

---

## API keys & accounts — what you'll need, and when

You do NOT need any accounts to do Phase 1 (what we just built). The test suite runs entirely offline on synthetic data.

For **Phase 2** (real data ingestion — next sprint), you'll need:

| Service     | Purpose                            | Cost                   | When        |
|-------------|------------------------------------|------------------------|-------------|
| **Polygon** | US equities historical + intraday  | ~$30/mo Starter; or $200/mo Stocks Developer for tick data | Sprint 2 |
| **Alpaca**  | Paper trading broker (later live)  | Paper = free. Live = $0 commissions | Sprint 4 |

When the time comes, Claude will:

1. Tell you exactly which signup page to open
2. Tell you which subscription tier to pick
3. Tell you what to paste into your `.env` file

You'll never have to figure out what an API key is or what "REST endpoint" means.

---

## The shape of our collaboration going forward

Inside this chat, Claude can:

- Write and edit every file in `alpha_factory/`
- Read your results, errors, and logs
- Design strategies, run analyses, generate reports
- Tell you exactly what to click next

You step in only when:

- A file needs to run on YOUR computer (we just did this — setup.ps1)
- An external service needs YOUR credentials (API signups)
- A real-money decision is being made (going from paper to live)
- You want to override a recommendation

Everything else is hands-off. Just paste me terminal output when I ask for it, and approve when I ask "ready to ship Sprint 2?"

---

## What NOT to do

- Don't run live trades from this code. We are months away from that. The risk policy and code both block it.
- Don't manually edit code unless Claude tells you what and why. Diffs without context create silent bugs.
- Don't paste API keys into the chat. Paste them into your `.env` file (Claude will tell you when).
- Don't open Claude Code CLI or use `/goal` mode for this project. You're in the right place already — Cowork desktop chat.

---

When you're ready, run `setup.ps1` and tell me what you see.
