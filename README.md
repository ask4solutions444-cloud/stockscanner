# SPANDANA Strategy Scanner — live NSE analyser (Upstox + Flask)

A Flask backend that pulls **real** NSE data from the Upstox API (daily
candles + live quotes), runs it through a swing / breakout / momentum /
positional strategy engine, and serves a dark trading-terminal style
frontend. No more simulated prices — this calls Upstox directly.

## What's inside
- `app.py` — Flask routes, OAuth login flow, data pipeline
- `upstox_client.py` — Upstox v2/v3 API wrapper (auth, quotes, historical candles, instrument lookup)
- `indicators.py` — EMA / RSI / MACD / ATR / volume-ratio math
- `strategy.py` — the 4 strategy scoring engines + default watchlist
- `templates/index.html` — the UI (calls your own `/api/...` endpoints, no client-side API keys)

## 1. Register an app on Upstox
1. Go to https://developer.upstox.com → create an app.
2. Set the **Redirect URI** to `https://<your-render-app>.onrender.com/callback`
   (you'll know this once you've picked a name on Render — see step 3).
3. Note down the **API Key (client_id)** and **API Secret (client_secret)**.

## 2. Important: Upstox access tokens expire daily
Upstox access tokens are valid until ~3:30am IST the *next* day, and Upstox
does not issue refresh tokens — a human has to complete the login screen
again each trading day. This app handles that with a `/login` route:

- Visit `https://<your-app>.onrender.com/login` once each morning.
- It redirects you to Upstox's login page (your TOTP/password, same as the
  Upstox app).
- Upstox redirects back to `/callback`, the app exchanges the code for a
  fresh access token, and you're live for the day.

The token is kept in memory only (not written to disk), so it resets on
every redeploy or Render restart too — you'll need to `/login` again after
those.

## 3. Deploy to Render
1. Push this folder to a GitHub repo.
2. On Render: **New → Web Service**, connect the repo. Render will read
   `render.yaml` automatically (or set Build Command
   `pip install -r requirements.txt` and Start Command
   `gunicorn app:app --bind 0.0.0.0:$PORT` manually).
3. In the service's **Environment** tab, add:
   - `UPSTOX_API_KEY`
   - `UPSTOX_API_SECRET`
   - `UPSTOX_REDIRECT_URI` = `https://<your-render-app>.onrender.com/callback`
   - `UPSTOX_ACCESS_TOKEN` = (optional) today's already-generated token, so
     the app is live immediately after deploy without a manual `/login`
4. Deploy. Go back to your Upstox app settings and make sure the Redirect
   URI matches exactly what you set in step 3.
5. Open the app. If the header shows "CONNECT UPSTOX", click it (or visit
   `/login`) and sign in.

## 4. Local dev
```bash
pip install -r requirements.txt
export UPSTOX_API_KEY=...
export UPSTOX_API_SECRET=...
export UPSTOX_REDIRECT_URI=http://localhost:5000/callback
python app.py
```
(For local testing you'll also need to add `http://localhost:5000/callback`
as a Redirect URI on your Upstox app, or generate a token elsewhere and set
`UPSTOX_ACCESS_TOKEN` directly.)

## How the data flows
- **Instrument lookup**: downloads Upstox's NSE instrument master
  (`assets.upstox.com/.../NSE.json.gz`) once every 12h, maps trading symbol
  → `instrument_key`.
- **History**: `GET /v3/historical-candle/{key}/days/1/{to}/{from}` — ~400
  days of daily OHLCV, cached 6h per symbol.
- **Live**: `GET /v2/market-quote/quotes` for last traded price, today's
  OHLC and volume, cached 15s. Today's live bar is folded into the daily
  series before indicators are computed, so RSI/MACD/EMA reflect the
  current move, not just yesterday's close.
- **Strategy engine** (`strategy.py`) scores each symbol 0–100 against 4
  setups and returns entry / stop-loss / target / signals / a plain-English
  recommendation — same logic as the original scanner, ported to Python.

## New: Market Direction, News, Backtests & PWA

**Market Direction panel** (`/api/direction`, `index_direction.py`) — runs the
5-signal confluence checklist (price vs VWAP, 20 EMA vs 50 EMA, RSI, MACD
crossover, breakout/breakdown on volume) against NIFTY, BANK NIFTY and
SENSEX, and only calls a direction when at least 4 of 5 signals agree —
otherwise it reports "WAIT". VWAP is computed from Upstox 15-minute
intraday candles.

**Market News** (`/api/news`, `news.py`) — pulls recent headlines from a few
public Indian financial RSS feeds (Economic Times Markets, Moneycontrol,
Livemint Markets, Business Standard Markets) and tags each headline
bullish/bearish/neutral with lightweight keyword matching (no paid
news/sentiment API needed). This doesn't require Upstox auth. RSS feed URLs
occasionally change on the publisher's side — if one starts erroring out,
just swap the URL in the `FEEDS` list in `news.py`; the others keep working
independently.

**Backtests** (`/api/backtest/<symbol>/<strategy>`, `backtest.py`) — replays
the same strategy rules used live against ~1 year of daily candles,
day-by-day with no lookahead, and reports win rate, average return per
trade, best/worst trade, and recent trade log. Click "📊 View backtest" on
any stock card to run it for that symbol + strategy. It's a simple
long-only, one-position, end-of-day-fill model meant to give a directional
read on how the rule set has been performing — not a substitute for a full
backtesting platform.

**PWA** — the app is installable (Add to Home Screen on mobile, install
icon in desktop Chrome/Edge). `static/manifest.json` + `static/sw.js` are
served at `/manifest.json` and `/sw.js`. The service worker caches static
assets only (icons, manifest) and always goes to the network first for
pages and `/api/*` calls, so you never see stale prices — it only serves a
cached response if you're fully offline.

## Customizing the watchlist
Edit `STRATEGY_STOCKS` in `strategy.py` to change which symbols get scanned
by "SCAN ALL". The search box (`/api/stock/<symbol>`) works for any NSE
equity symbol Upstox has in its instrument master, regardless of watchlist.

## Disclaimer
Not SEBI-registered investment advice. Entry/SL/target levels are generated
by a simple rules-based scoring model for informational purposes only —
verify everything and apply your own risk management before trading.
