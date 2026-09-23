# FLOW TERMINAL 🌐

A terminal-style dashboard that tracks stocks, commodities, crypto and newly launched
meme tokens, estimates **where capital is flowing**, and generates **setups**
(LONG / SHORT / WAIT with entry, stop and target).

**For informational purposes only.** It is not connected to any broker and places no orders.

## What it does

| Module | What it shows | Source |
|---|---|---|
| 1 BRIEF | Capital flow by asset class / sector / market centre, the 3 cleanest setups, trending coins | yfinance, CoinGecko |
| 2 CHART | Candlestick + SMA20/50 + entry/stop/target for any asset (`GIP GOLD`) | yfinance |
| 3 GLOBE | 3D globe of 18 financial centres; colour = inflow/outflow, arcs = rotation | yfinance (country ETFs) |
| 4 SETUPS | LONG/SHORT/WAIT table across 60+ assets with conviction and rationale | yfinance |
| 5 STOCKS | Stock watchlist with sparklines; add your own tickers | yfinance |
| 6 COMMODITIES | 20 commodities (metals, energy, agriculture) with sparklines + flow | yfinance futures |
| 7 CRYPTO | Top 100, BTC dominance, flow within crypto | CoinGecko |
| 8 MEME RADAR | New tokens (Solana/Base/ETH/BSC) with a network score and security flags | DexScreener, RugCheck, GoPlus |
| 9 FX & RATES | Indices, DXY, EUR/USD, US10Y, VIX | yfinance |
| ASK | Free-text question answered from a market snapshot (optionally via the Claude API) | — |

**Commands** (the command bar at the top, Bloomberg-style):
`GIP GOLD` · `DES US30` · `SET OIL` · `VER DAX` · `GIP NVDA` · `GIP BTC` · `MEME WIF` · `ASK what should I watch today?`

## How to read the screen

**Flow bars (BRIEF, COMMODITIES).** Every asset gets a score from −100 to +100:

| Component | Weight | What it measures |
|---|---|---|
| Relative strength | 50% | 1d/5d/20d/60d returns **relative to every other asset** in the group (cross-sectional z-scores) |
| Trend | 30% | Price above/below SMA20 and SMA50, and SMA20 vs SMA50 |
| Flow proxy | 20% | 5-day dollar volume / 60-day average, signed by the 5-day return |

- **Green bar, positive number** = inflow. Money is favouring this asset over the rest.
- **Red bar, negative number** = outflow.
- Above +25 = INFLOW, below −25 = OUTFLOW, in between = NEUTRAL.
- It is a **relative** ranking: in a market where everything falls, the "best" asset may
  just be falling less. Check the breadth line in the "IN PLAIN WORDS" panel.

**Setups.** Trend (±35) + RSI(14) (±15) + volume confirmation (±10) + rotation score × 0.3.
Above +25 → LONG, below −25 → SHORT, otherwise WAIT. Conviction is the absolute value.
Stop = 2×ATR(14), target = 3×ATR → R:R 1.5. ATR% shows how volatile the asset is.

**Meme score (0–100).** Liquidity (20) + volume/liquidity (15) + buy pressure (20) + momentum (15)
+ age (10) + website/socials/boosts (10), minus security penalties. A honeypot scores 0.
Grade A ≥ 75. The score says "real activity, few red flags", **not** "it will go up".

Code: `engine/rotation.py`, `engine/signals.py`, `engine/meme.py`.

## Data freshness

| Data | Refresh in the app | Delay at the source |
|---|---|---|
| Daily history (bars, setups, cards) | every 5 min | futures/FX < 1 min, US stocks ~15 min |
| Crypto | every 2 min | real-time |
| Meme radar | every 3 min or the "NEW SCAN" button | real-time |

There is no free API for real ETF flows, so FLOW is a proxy. CoinGecko's free tier allows
~30 requests/minute; if you see an empty panel, wait a minute.

---

## A. Run it on Windows

1. Install **Python 3.12** from https://www.python.org/downloads/windows/ and tick
   **"Add python.exe to PATH"** in the installer.
2. Unzip `flow-terminal-en.zip`. Open the folder that directly contains `app.py`.
3. Double-click **`run.bat`**. The first launch creates a virtual environment and installs
   the libraries (2–4 minutes), then opens `http://localhost:8501` in your browser.
   Later launches take about 10 seconds. Close the black window to stop the app.

Manual alternative (PowerShell in the project folder):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m streamlit run app.py
```
- `streamlit is not recognized` → always use `python -m streamlit run app.py`.
- `File does not exist: app.py` → you are in the wrong folder; `cd` into the one with `app.py`.
- `running scripts is disabled` → `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Optional LLM for ASK: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
and add your `ANTHROPIC_API_KEY`. Without a key, ASK answers from the terminal's rules.

Offline tests: `pip install pytest` then `python -m pytest tests`.

## B. Push to GitHub

1. On github.com: **+** → **New repository** → name `flow-terminal` → Public → **no** README → Create.
2. In PowerShell, inside the project folder (replace `YOUR_USERNAME`):
   ```powershell
   git init
   git add .
   git commit -m "FLOW TERMINAL"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/flow-terminal.git
   git push -u origin main
   ```
   `.gitignore` keeps `.venv` and `secrets.toml` out. Never commit an API key.

## C. Deploy as an app (Streamlit Community Cloud, free)

1. https://share.streamlit.io → **Continue with GitHub**.
2. **Create app** → repo `flow-terminal`, branch `main`, main file `app.py` → **Deploy**.
3. Optional: App settings → **Secrets** → paste `ANTHROPIC_API_KEY = "..."`.
4. After 2–4 minutes you get a URL like `https://YOUR_USERNAME-flow-terminal.streamlit.app`.
5. iPhone: open it in Safari → Share → **Add to Home Screen**.
   Windows: Chrome → ⋮ → Cast, save and share → **Install page as app**.
6. Every `git push` redeploys automatically.

The free tier sleeps after inactivity; the first open then takes ~30 seconds.

---

## Structure

```
app.py                  UI, command bar, modules
engine/data.py          fetchers (yfinance, CoinGecko, DexScreener, GoPlus, RugCheck) + universe
engine/rotation.py      capital-rotation engine
engine/signals.py       setup generator
engine/meme.py          meme radar
engine/narrative.py     "in plain words" text + optional LLM
ui/theme.py             terminal CSS
ui/components.py        cards, globe, chart, ticker tape
tests/                  offline tests with mocked data
.streamlit/config.toml  dark theme
run.bat                 one-click launcher for Windows
```

## Upgrade path

1. **Backtest the setups**: log every signal to SQLite and measure hit-rate and expectancy
   per asset class. This turns the dashboard into research.
2. **Real flows**: add ETF.com creations/redemptions or SEC 13F data as a 4th rotation factor.
3. **Validate the meme radar**: store every scan and measure the 24h/72h forward return per grade.
4. **Real-time US equities**: an Alpaca or Polygon websocket instead of yfinance.
5. **LLM with tools**: give ASK function calling so it can pull history on its own.
