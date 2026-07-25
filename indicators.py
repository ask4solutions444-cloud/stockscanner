"""Technical indicator calculations (pure Python, no numpy dependency)."""


def ema(values, n):
    """Exponential moving average. Returns a list same length as values,
    with leading entries None until the seed window is filled."""
    if not values or len(values) < 2:
        return [values[-1] if values else 0]
    n = min(n, len(values))
    k = 2 / (n + 1)
    seed = sum(values[:n]) / n
    out = []
    v = seed
    for i, x in enumerate(values):
        if i < n - 1:
            out.append(None)
        elif i == n - 1:
            out.append(v)
        else:
            v = x * k + v * (1 - k)
            out.append(v)
    return out


def rsi(closes, n=14):
    if not closes or len(closes) < n + 2:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / n
    avg_loss = losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(d, 0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-d, 0)) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def macd(closes):
    if not closes or len(closes) < 35:
        return {"hist": 0.0, "line": 0.0, "sig": 0.0}
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    ml = [(v - w) if (v is not None and w is not None) else 0 for v, w in zip(e12, e26)]
    valid = [v for v in ml if v != 0][-30:] or ml[-30:]
    sg = ema(valid, 9)
    lm = ml[-1]
    ls = sg[-1] if sg and sg[-1] is not None else 0
    return {"hist": lm - ls, "line": lm, "sig": ls}


def atr(highs, lows, closes, n=14):
    if not highs or len(highs) < 2:
        return (closes[-1] if closes else 100) * 0.02
    trs = []
    for i in range(1, min(len(highs), len(lows), len(closes))):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    window = trs[-n:]
    return sum(window) / len(window) if window else (closes[-1] if closes else 100) * 0.02


def vol_ratio(vols, avg_vol=0):
    if avg_vol and avg_vol > 0:
        return (vols[-1] if vols else 0) / avg_vol
    if not vols or len(vols) < 5:
        return 1.0
    window = vols[-21:-1] if len(vols) > 20 else vols[:-1]
    avg = sum(window) / len(window) if window else 0
    return (vols[-1] / avg) if avg > 0 else 1.0
