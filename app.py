import os
import time

from flask import Flask, jsonify, redirect, render_template, request

from strategy import STRATEGY_STOCKS, STRATEGIES, STOCK_NAMES, analyse
from upstox_client import upstox, UpstoxError, INDEX_KEYS

app = Flask(__name__)

# ── tiny in-memory caches (per dyno) ──────────────────────────────────
_daily_cache = {}      # symbol -> (ts, candles)
_quote_cache = {}      # instrument_key -> (ts, quote)
DAILY_TTL = 6 * 3600    # daily candles barely change intraday
QUOTE_TTL = 15          # live-ish


def _cached_daily(symbol, ikey):
    now = time.time()
    hit = _daily_cache.get(symbol)
    if hit and now - hit[0] < DAILY_TTL:
        return hit[1]
    candles = upstox.get_daily_candles(ikey, days=400)
    _daily_cache[symbol] = (now, candles)
    return candles


def _cached_quotes(instrument_keys):
    now = time.time()
    need = [k for k in instrument_keys if k not in _quote_cache or now - _quote_cache[k][0] >= QUOTE_TTL]
    if need:
        fresh = upstox.get_quotes(need)
        for k, v in fresh.items():
            _quote_cache[k] = (now, v)
    out = {}
    for k in instrument_keys:
        hit = _quote_cache.get(k)
        if hit:
            out[k] = hit[1]
    return out


def _find_quote(quotes_by_response_key, symbol, ikey):
    """Upstox keys the response dict by 'EXCHANGE:SYMBOL' or similar - match loosely."""
    for k, v in quotes_by_response_key.items():
        if v.get("instrument_token") == ikey:
            return v
    for k, v in quotes_by_response_key.items():
        if k.upper().endswith(":" + symbol.upper()) or k.upper() == symbol.upper():
            return v
    if quotes_by_response_key:
        return next(iter(quotes_by_response_key.values()))
    return None


def build_stock_data(symbol):
    """Fetch daily candles + a live quote for `symbol` and assemble the
    closes/highs/lows/volumes structure the strategy engine expects."""
    ikey = upstox.instrument_key(symbol)
    if not ikey:
        return None

    candles = _cached_daily(symbol, ikey)
    if not candles or len(candles) < 15:
        return None

    # candle format: [timestamp, open, high, low, close, volume, oi] oldest->newest
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    vols = [c[5] for c in candles]

    quotes = _cached_quotes([ikey])
    q = _find_quote(quotes, symbol, ikey)

    prev_close_hist = closes[-1]
    if q:
        price = q.get("last_price") or prev_close_hist
        ohlc = q.get("ohlc") or {}
        prev_close = ohlc.get("close") or prev_close_hist
        net_change = q.get("net_change")
        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
        today_vol = q.get("volume") or 0
        # Fold today's live move into the series so indicators reflect it.
        today_high = max(ohlc.get("high") or price, price)
        today_low = min(ohlc.get("low") or price, price) if ohlc.get("low") else price
        closes = closes + [price]
        highs = highs + [today_high]
        lows = lows + [today_low]
        vols = vols + [today_vol]
    else:
        price = prev_close_hist
        prev_close = closes[-2] if len(closes) > 1 else prev_close_hist
        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0

    window = closes[-370:]
    hwindow = highs[-370:]
    lwindow = lows[-370:]
    week52_high = max(hwindow) if hwindow else max(closes)
    week52_low = min(lwindow) if lwindow else min(closes)
    avg_vol = sum(vols[-21:-1]) / max(1, len(vols[-21:-1])) if len(vols) > 1 else (vols[-1] if vols else 0)

    return {
        "symbol": symbol,
        "source": "live",
        "price": round(price, 2),
        "previousClose": round(prev_close, 2),
        "changePct": change_pct,
        "week52High": round(week52_high, 2),
        "week52Low": round(week52_low, 2),
        "avgVol": avg_vol,
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volumes": vols,
    }


def _auth_error_response():
    return jsonify({
        "error": "not_authenticated",
        "message": "Upstox access token missing or expired. Visit /login to authenticate.",
        "login_url": "/login",
    }), 401


# ── pages ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template(
        "index.html",
        strategies=STRATEGIES,
        strategy_stocks=STRATEGY_STOCKS,
        authenticated=upstox.is_authenticated(),
    )


# ── auth ───────────────────────────────────────────────────────────────
@app.route("/login")
def login():
    if not upstox.api_key or not upstox.redirect_uri:
        return "UPSTOX_API_KEY / UPSTOX_REDIRECT_URI not configured on the server.", 500
    return redirect(upstox.login_url())


@app.route("/callback")
def callback():
    code = request.args.get("code")
    err = request.args.get("error")
    if err:
        return f"Upstox login failed: {err}", 400
    if not code:
        return "Missing authorization code from Upstox.", 400
    try:
        upstox.exchange_code(code)
    except UpstoxError as e:
        return f"Token exchange failed: {e}", 400
    return redirect("/")


@app.route("/api/status")
def api_status():
    return jsonify({
        "authenticated": upstox.is_authenticated(),
        "token_age_seconds": (time.time() - upstox.token_obtained_at) if upstox.token_obtained_at else None,
    })


# ── data API ──────────────────────────────────────────────────────────
@app.route("/api/indices")
def api_indices():
    if not upstox.is_authenticated():
        return _auth_error_response()
    try:
        keys = list(INDEX_KEYS.values())
        quotes = _cached_quotes(keys)
        out = {}
        for name, ikey in INDEX_KEYS.items():
            q = _find_quote(quotes, name, ikey)
            if not q:
                continue
            price = q.get("last_price")
            prev = (q.get("ohlc") or {}).get("close")
            chg = round((price - prev) / prev * 100, 2) if price and prev else 0
            out[name] = {"price": price, "changePct": chg}
        return jsonify(out)
    except UpstoxError:
        return _auth_error_response()


@app.route("/api/stock/<symbol>")
def api_stock(symbol):
    if not upstox.is_authenticated():
        return _auth_error_response()
    symbol = symbol.strip().upper()
    try:
        raw = build_stock_data(symbol)
    except UpstoxError:
        return _auth_error_response()
    if not raw:
        return jsonify({"error": "not_found", "message": f"No NSE equity found for '{symbol}'."}), 404

    analyses = {}
    for strat in STRATEGIES:
        r = analyse(raw, strat)
        if r:
            analyses[strat] = r
    return jsonify({
        "symbol": symbol,
        "name": STOCK_NAMES.get(symbol, symbol),
        "price": raw["price"],
        "changePct": raw["changePct"],
        "source": raw["source"],
        "strategies": analyses,
    })


@app.route("/api/scan")
def api_scan():
    if not upstox.is_authenticated():
        return _auth_error_response()

    sym_map = {}
    for strat, syms in STRATEGY_STOCKS.items():
        for s in syms:
            sym_map.setdefault(s, []).append(strat)

    result = {strat: [] for strat in STRATEGIES}
    errors = []
    for symbol, strats in sym_map.items():
        try:
            raw = build_stock_data(symbol)
        except UpstoxError:
            return _auth_error_response()
        if not raw:
            errors.append(symbol)
            continue
        for strat in strats:
            r = analyse(raw, strat)
            if r:
                result[strat].append(r)

    return jsonify({"data": result, "errors": errors})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
