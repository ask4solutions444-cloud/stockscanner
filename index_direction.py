"""Confluence-based direction call for indices (or any symbol), matching the
"High-probability Call/Put setup" checklist:

  Call setup (bullish):           Put setup (bearish):
  - Price above VWAP              - Price below VWAP
  - 20 EMA above 50 EMA           - 20 EMA below 50 EMA
  - RSI above 60                  - RSI below 40
  - Bullish MACD crossover        - Bearish MACD crossover
  - Breakout with high volume     - Breakdown with high volume

Rule of thumb: wait until at least 4 of these 5 signals agree before calling
a direction; otherwise it's a "wait / mixed" read.
"""
from indicators import ema, rsi, macd, vol_ratio

CONFLUENCE_THRESHOLD = 4  # out of 5


def _vwap(intraday_candles):
    """intraday_candles: [timestamp, open, high, low, close, volume, oi], oldest->newest."""
    cum_pv = 0.0
    cum_vol = 0.0
    for c in intraday_candles:
        _, o, h, l, cl, v = c[0], c[1], c[2], c[3], c[4], c[5]
        typical = (h + l + cl) / 3
        cum_pv += typical * (v or 0)
        cum_vol += (v or 0)
    return (cum_pv / cum_vol) if cum_vol else None


def confluence_signal(name, daily_candles, intraday_candles, live_price=None):
    """daily_candles / intraday_candles: [ts,o,h,l,c,v,oi] oldest->newest.
    Returns a dict describing each of the 5 checks plus an overall verdict."""
    if not daily_candles or len(daily_candles) < 30:
        return None

    closes = [c[4] for c in daily_candles]
    highs = [c[2] for c in daily_candles]
    lows = [c[3] for c in daily_candles]
    vols = [c[5] for c in daily_candles]

    price = live_price if live_price is not None else closes[-1]

    e20 = ema(closes, 20)
    e50 = ema(closes, min(50, len(closes) - 1))
    e20v = next((v for v in reversed(e20) if v is not None), price)
    e50v = next((v for v in reversed(e50) if v is not None), price)
    rv = rsi(closes)
    md = macd(closes)
    avg_vol = sum(vols[-21:-1]) / max(1, len(vols[-21:-1])) if len(vols) > 1 else (vols[-1] if vols else 0)
    vr = vol_ratio(vols, avg_vol)
    vwap = _vwap(intraday_candles) if intraday_candles else None
    recent_high = max(highs[-10:]) if len(highs) >= 10 else max(highs)
    recent_low = min(lows[-10:]) if len(lows) >= 10 else min(lows)

    checks = []

    # 1. VWAP
    if vwap:
        checks.append({
            "label": "Price above VWAP" if price > vwap else "Price below VWAP",
            "dir": "bull" if price > vwap else "bear",
            "detail": f"LTP {price:.1f} vs VWAP {vwap:.1f}",
        })
    else:
        checks.append({"label": "VWAP unavailable (no intraday data)", "dir": "neutral", "detail": ""})

    # 2. EMA20 vs EMA50
    checks.append({
        "label": "20 EMA above 50 EMA" if e20v > e50v else "20 EMA below 50 EMA",
        "dir": "bull" if e20v > e50v else "bear",
        "detail": f"EMA20 {e20v:.1f} vs EMA50 {e50v:.1f}",
    })

    # 3. RSI
    if rv > 60:
        checks.append({"label": "RSI above 60", "dir": "bull", "detail": f"RSI {rv}"})
    elif rv < 40:
        checks.append({"label": "RSI below 40", "dir": "bear", "detail": f"RSI {rv}"})
    else:
        checks.append({"label": f"RSI neutral ({rv})", "dir": "neutral", "detail": f"RSI {rv}"})

    # 4. MACD crossover
    checks.append({
        "label": "Bullish MACD crossover" if md["hist"] > 0 else "Bearish MACD crossover",
        "dir": "bull" if md["hist"] > 0 else "bear",
        "detail": f"hist {md['hist']:.2f}",
    })

    # 5. Breakout/breakdown with high volume
    if vr >= 1.5 and price >= recent_high * 0.998:
        checks.append({"label": "Breakout with high volume", "dir": "bull", "detail": f"vol {vr:.1f}x, near 10D high"})
    elif vr >= 1.5 and price <= recent_low * 1.002:
        checks.append({"label": "Breakdown with high volume", "dir": "bear", "detail": f"vol {vr:.1f}x, near 10D low"})
    else:
        checks.append({"label": f"No high-volume break ({vr:.1f}x)", "dir": "neutral", "detail": ""})

    bull_count = sum(1 for c in checks if c["dir"] == "bull")
    bear_count = sum(1 for c in checks if c["dir"] == "bear")

    if bull_count >= CONFLUENCE_THRESHOLD:
        verdict, verdict_type = "HIGH-PROBABILITY CALL SETUP", "buy"
    elif bear_count >= CONFLUENCE_THRESHOLD:
        verdict, verdict_type = "HIGH-PROBABILITY PUT SETUP", "sell"
    else:
        verdict, verdict_type = "WAIT — signals mixed (need 4 of 5 aligned)", "watch"

    return {
        "name": name,
        "price": round(price, 2),
        "checks": checks,
        "bullCount": bull_count,
        "bearCount": bear_count,
        "verdict": verdict,
        "verdictType": verdict_type,
    }
