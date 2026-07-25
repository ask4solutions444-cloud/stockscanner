"""Walk-forward backtest of the strategy engine against historical daily
candles. At each past day we only feed the engine data up to that day (no
lookahead), take the trade if it says BUY, then check the following bars to
see whether target or stop-loss was hit first, or the strategy's holding
period ran out first.

This is intentionally simple (long-only, one open position per signal,
end-of-day fills) - it's meant to give a directional sense of how the rule
set has performed recently, not a production-grade backtester.
"""
from strategy import analyse

# Approx trading-day holding windows per strategy, used to force an exit
# if neither target nor stop-loss is hit first.
HOLD_DAYS = {
    "swing": 10,
    "breakout": 15,
    "momentum": 20,
    "positional": 90,
}

MIN_HISTORY = 40  # bars of warm-up before we start taking signals


def run_backtest(daily_candles, strategy, symbol="", lookback_bars=350):
    """daily_candles: [ts,o,h,l,c,v,oi] oldest->newest (>= ~120 bars ideal)."""
    closes = [c[4] for c in daily_candles]
    highs = [c[2] for c in daily_candles]
    lows = [c[3] for c in daily_candles]
    vols = [c[5] for c in daily_candles]
    n = len(closes)
    if n < MIN_HISTORY + 10:
        return {"symbol": symbol, "strategy": strategy, "trades": 0, "error": "not enough history"}

    start = max(MIN_HISTORY, n - lookback_bars)
    hold = HOLD_DAYS.get(strategy, 15)

    trades = []
    i = start
    while i < n - 1:
        window_closes = closes[: i + 1]
        window_highs = highs[: i + 1]
        window_lows = lows[: i + 1]
        window_vols = vols[: i + 1]
        avg_vol = sum(window_vols[-21:-1]) / max(1, len(window_vols[-21:-1])) if len(window_vols) > 1 else 0

        stock = {
            "symbol": symbol, "source": "hist",
            "price": window_closes[-1],
            "previousClose": window_closes[-2] if len(window_closes) > 1 else window_closes[-1],
            "changePct": 0,
            "week52High": max(window_highs[-370:]),
            "week52Low": min(window_lows[-370:]),
            "avgVol": avg_vol,
            "closes": window_closes, "highs": window_highs,
            "lows": window_lows, "volumes": window_vols,
        }
        r = analyse(stock, strategy)
        if r and r["recType"] == "buy":
            entry, sl, target = r["entry"], r["sl"], r["target"]
            exit_idx = min(i + hold, n - 1)
            outcome, exit_price, exit_day_offset = "timeout", closes[exit_idx], exit_idx - i
            for j in range(i + 1, exit_idx + 1):
                if lows[j] <= sl:
                    outcome, exit_price, exit_day_offset = "stop_loss", sl, j - i
                    break
                if highs[j] >= target:
                    outcome, exit_price, exit_day_offset = "target", target, j - i
                    break
            ret_pct = round((exit_price - entry) / entry * 100, 2)
            trades.append({
                "entryDay": i, "entry": entry, "sl": sl, "target": target,
                "exit": round(exit_price, 2), "outcome": outcome,
                "returnPct": ret_pct, "daysHeld": exit_day_offset,
            })
            i = i + max(exit_day_offset, 1)
        else:
            i += 1

    if not trades:
        return {"symbol": symbol, "strategy": strategy, "trades": 0}

    wins = [t for t in trades if t["returnPct"] > 0]
    losses = [t for t in trades if t["returnPct"] <= 0]
    total_ret = sum(t["returnPct"] for t in trades)
    avg_ret = round(total_ret / len(trades), 2)
    win_rate = round(len(wins) / len(trades) * 100, 1)
    avg_win = round(sum(t["returnPct"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(t["returnPct"] for t in losses) / len(losses), 2) if losses else 0
    best = max(trades, key=lambda t: t["returnPct"])
    worst = min(trades, key=lambda t: t["returnPct"])

    return {
        "symbol": symbol,
        "strategy": strategy,
        "trades": len(trades),
        "winRate": win_rate,
        "avgReturnPct": avg_ret,
        "avgWinPct": avg_win,
        "avgLossPct": avg_loss,
        "bestTradePct": best["returnPct"],
        "worstTradePct": worst["returnPct"],
        "cumulativeReturnPct": round(total_ret, 2),
        "recentTrades": trades[-8:],
    }
