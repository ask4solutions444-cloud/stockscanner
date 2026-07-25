"""Strategy engine: turns raw OHLCV data into swing/breakout/momentum/positional
trade setups. This is a direct Python port of the original client-side JS logic."""

from indicators import ema, rsi, macd, atr, vol_ratio

STRATEGY_STOCKS = {
    "swing": ["RELIANCE", "ICICIBANK", "TATAMOTORS", "LT", "BHARTIARTL"],
    "breakout": ["ADANIPORTS", "HDFCBANK", "SUNPHARMA", "INFY", "NTPC"],
    "momentum": ["TCS", "WIPRO", "AXISBANK", "MARUTI", "BAJFINANCE"],
    "positional": ["POLYCAB", "COFORGE", "CUMMINSIND", "MAZDOCK", "SOLARINDS"],
}

STOCK_NAMES = {
    "RELIANCE": "Reliance Industries", "ICICIBANK": "ICICI Bank", "TATAMOTORS": "Tata Motors",
    "LT": "Larsen & Toubro", "BHARTIARTL": "Bharti Airtel", "ADANIPORTS": "Adani Ports",
    "HDFCBANK": "HDFC Bank", "SUNPHARMA": "Sun Pharma", "INFY": "Infosys", "NTPC": "NTPC Ltd",
    "TCS": "Tata Consultancy Services", "WIPRO": "Wipro Ltd", "AXISBANK": "Axis Bank",
    "MARUTI": "Maruti Suzuki", "BAJFINANCE": "Bajaj Finance", "POLYCAB": "Polycab India",
    "COFORGE": "Coforge Ltd", "CUMMINSIND": "Cummins India", "MAZDOCK": "Mazagon Dock",
    "SOLARINDS": "Solar Industries", "SBIN": "State Bank of India", "TATASTEEL": "Tata Steel",
    "HCLTECH": "HCL Technologies", "NESTLEIND": "Nestle India", "ULTRACEMCO": "UltraTech Cement",
}

STRATEGIES = {
    "swing": {"label": "SWING TRADE", "period": "2\u201315 Days", "target": "3\u20138%", "emoji": "\u26a1"},
    "breakout": {"label": "BREAKOUT", "period": "1\u20133 Weeks", "target": "5\u201310%", "emoji": "\U0001f680"},
    "momentum": {"label": "MOMENTUM", "period": "2\u20134 Weeks", "target": "5\u201312%", "emoji": "\U0001f4c8"},
    "positional": {"label": "POSITIONAL", "period": "1\u20136 Months", "target": "10\u201325%", "emoji": "\U0001f3d7\ufe0f"},
}


def r2(x):
    return round(x, 2)


def analyse(stock, strat):
    """stock: dict with closes/highs/lows/volumes/price/previousClose/changePct/
    week52High/week52Low/avgVol/symbol/source. Returns a dict describing the
    trade setup for the given strategy, or None if there isn't enough data."""
    closes = stock.get("closes") or []
    if len(closes) < 15:
        return None
    highs = stock.get("highs") or []
    lows = stock.get("lows") or []
    vols = stock.get("volumes") or []
    symbol = stock.get("symbol")
    source = stock.get("source", "live")

    cp = r2(stock.get("price") or closes[-1])
    pv = r2(stock.get("previousClose") or (closes[-2] if len(closes) > 1 else cp))
    pct = round(stock.get("changePct") if stock.get("changePct") is not None
                else ((cp - pv) / pv * 100 if pv else 0), 2)

    e20 = ema(closes, 20)
    e50 = ema(closes, min(50, len(closes) - 1))
    e20v = next((v for v in reversed(e20) if v is not None), cp)
    e50v = next((v for v in reversed(e50) if v is not None), cp)
    rv = rsi(closes)
    md = macd(closes)
    at = atr(highs, lows, closes)
    vr = vol_ratio(vols, stock.get("avgVol") or 0)
    h52 = stock.get("week52High") or (max(highs) if highs else cp)
    l52 = stock.get("week52Low") or (min(lows) if lows else cp)
    pf52 = round((cp - h52) / h52 * 100, 1) if h52 else 0
    bull = e20v > e50v
    ab_e20 = cp > e20v
    ab_e50 = cp > e50v

    sigs = []
    entry = sl = target = None
    rec = rtype = hold = None

    if strat == "swing":
        hold = "5\u201310 trading days"
        entry, sl, target = cp, r2(cp - at * 1.5), r2(cp + at * 3)
        sigs.append({"t": "EMA BULL \u2713", "c": "bull"} if bull else {"t": "EMA BEAR", "c": "bear"})
        if 40 <= rv <= 65:
            sigs.append({"t": f"RSI {rv} \u2713", "c": "bull"})
        elif 65 < rv < 75:
            sigs.append({"t": f"RSI {rv}", "c": "bull"})
        elif rv >= 75:
            sigs.append({"t": f"RSI {rv} OB", "c": "bear"})
        else:
            sigs.append({"t": f"RSI {rv} OS", "c": "bull"})
        sigs.append({"t": "MACD \u25b2", "c": "bull"} if md["hist"] > 0 else {"t": "MACD \u25bc", "c": "bear"})
        sigs.append({"t": ">EMA20", "c": "bull"} if ab_e20 else {"t": "<EMA20", "c": "bear"})
        b = sum(1 for s in sigs if s["c"] == "bull")
        score = round(b / len(sigs) * 100)
        if score >= 75 and rv < 75:
            rec = f"BUY near \u20b9{e20v:.0f} (EMA20). RSI={rv} \u2014 ideal zone. Trail SL below each swing low."
            rtype = "buy"
        elif score >= 50:
            rec = f"WATCH. Trend {'bullish' if bull else 'mixed'}. Wait for RSI 45\u201362 & close above EMA20 (\u20b9{e20v:.0f})."
            rtype = "watch"
        else:
            rec = f"AVOID. RSI={rv}, {'above' if ab_e20 else 'below'} EMA20, MACD {'+' if md['hist']>0 else '-'}. No clean setup yet."
            rtype = "sell"

    elif strat == "breakout":
        hold = "1\u20133 weeks"
        rh = max(highs[-5:]) if len(highs) >= 5 else cp
        entry, sl, target = r2(rh * 1.005), r2(cp * 0.95), r2(cp * 1.10)
        if vr >= 1.8:
            sigs.append({"t": f"VOL {vr:.1f}x \U0001f525", "c": "bull"})
        elif vr >= 1.2:
            sigs.append({"t": f"VOL {vr:.1f}x", "c": "neutral"})
        else:
            sigs.append({"t": "VOL LOW", "c": "bear"})
        if pf52 > -3:
            sigs.append({"t": "AT 52W HIGH", "c": "bull"})
        elif pf52 > -8:
            sigs.append({"t": f"{abs(pf52)}% FR HIGH", "c": "neutral"})
        else:
            sigs.append({"t": f"{abs(pf52)}% BELOW", "c": "bear"})
        sigs.append({"t": ">EMA20", "c": "bull"} if ab_e20 else {"t": "<EMA20", "c": "bear"})
        if 55 < rv < 75:
            sigs.append({"t": f"RSI {rv}", "c": "bull"})
        elif rv >= 75:
            sigs.append({"t": f"RSI {rv} OB", "c": "bear"})
        else:
            sigs.append({"t": f"RSI {rv}", "c": "neutral"})
        sigs.append({"t": "MACD +", "c": "bull"} if md["hist"] > 0 else {"t": "MACD \u2013", "c": "neutral"})
        b = sum(1 for s in sigs if s["c"] == "bull")
        score = round(b / len(sigs) * 100)
        if score >= 60 and vr >= 1.5 and ab_e20:
            rec = f"BREAKOUT SET. Vol {vr:.1f}x. Buy above \u20b9{entry} \u00b7 SL \u20b9{sl} \u00b7 Target \u20b9{target}."
            rtype = "buy"
        elif vr < 1.3:
            rec = f"LOW VOLUME ({vr:.1f}x). Wait for 1.8x+ volume surge before entering breakout."
            rtype = "watch"
        else:
            rec = f"WATCH. Set alert above \u20b9{rh:.0f}. Need {'better signals' if score<60 else 'volume confirmation'}."
            rtype = "watch"

    elif strat == "momentum":
        hold = "2\u20134 weeks"
        entry, sl, target = cp, r2(cp - at * 2), r2(cp + at * 4)
        if 60 < rv < 80:
            sigs.append({"t": f"RSI {rv} \U0001f525", "c": "bull"})
        elif rv >= 80:
            sigs.append({"t": f"RSI {rv} OB", "c": "bear"})
        elif rv > 50:
            sigs.append({"t": f"RSI {rv}", "c": "neutral"})
        else:
            sigs.append({"t": f"RSI {rv} WEAK", "c": "bear"})
        if md["hist"] > 0 and md["line"] > 0:
            sigs.append({"t": "MACD STRONG", "c": "bull"})
        elif md["hist"] > 0:
            sigs.append({"t": "MACD CROSS+", "c": "bull"})
        else:
            sigs.append({"t": "MACD BEAR", "c": "bear"})
        if ab_e20 and ab_e50:
            sigs.append({"t": "ABOVE EMA20+50", "c": "bull"})
        elif ab_e20:
            sigs.append({"t": ">EMA20", "c": "bull"})
        else:
            sigs.append({"t": "<EMA20", "c": "bear"})
        if vr >= 1.5:
            sigs.append({"t": f"VOL {vr:.1f}x", "c": "bull"})
        elif vr >= 1.0:
            sigs.append({"t": f"VOL {vr:.1f}x", "c": "neutral"})
        else:
            sigs.append({"t": "LOW VOL", "c": "bear"})
        sigs.append({"t": f"+{pct}% TODAY", "c": "bull"} if pct > 0 else {"t": f"{pct}% TODAY", "c": "bear"})
        b = sum(1 for s in sigs if s["c"] == "bull")
        score = round(b / len(sigs) * 100)
        if score >= 70 and rv > 55:
            rec = f"STRONG MOMENTUM. Enter \u20b9{cp} on 1% dip to EMA20. RSI={rv}. Trail SL by ATR."
            rtype = "buy"
        elif score >= 50:
            rec = f"MODERATE. RSI={rv}. Wait for RSI>60 + MACD positive crossover to enter."
            rtype = "watch"
        else:
            rec = f"WEAK. RSI={rv}, MACD {'barely+' if md['hist']>0 else '-'}. Avoid \u2014 wait for RSI reset to 45\u201350."
            rtype = "sell"

    elif strat == "positional":
        hold = "1\u20136 months"
        entry, sl, target = cp, r2(cp * 0.92), r2(cp * 1.20)
        if bull and ab_e50:
            sigs.append({"t": "UPTREND \u2713", "c": "bull"})
        elif bull:
            sigs.append({"t": "EMA BULL", "c": "bull"})
        else:
            sigs.append({"t": "DOWNTREND", "c": "bear"})
        if 40 <= rv <= 65:
            sigs.append({"t": f"RSI {rv} HEALTHY", "c": "bull"})
        elif 65 < rv < 75:
            sigs.append({"t": f"RSI {rv}", "c": "neutral"})
        elif rv >= 75:
            sigs.append({"t": f"RSI {rv} OB", "c": "bear"})
        else:
            sigs.append({"t": f"RSI {rv} WEAK", "c": "bear"})
        if pf52 > -10:
            sigs.append({"t": "STRONG RANGE", "c": "bull"})
        elif pf52 > -20:
            sigs.append({"t": "MID RANGE", "c": "neutral"})
        else:
            sigs.append({"t": "DEEP CORR", "c": "neutral"})
        sigs.append({"t": "MACD +", "c": "bull"} if md["hist"] > 0 else {"t": "MACD \u2013", "c": "bear"})
        sigs.append({"t": "VOL ADEQUATE", "c": "bull"} if vr >= 1.0 else {"t": "LOW VOL", "c": "neutral"})
        b = sum(1 for s in sigs if s["c"] == "bull")
        score = round(b / len(sigs) * 100)
        if score >= 70 and bull:
            rec = f"STRONG POSITIONAL. Accumulate in 2\u20133 tranches. SL \u20b9{sl} (8%). Target \u20b9{target} in 3\u20136M."
            rtype = "buy"
        elif score >= 50:
            rec = f"WATCHLIST CANDIDATE. Wait for Q-results or sector momentum. SL \u20b9{sl}, T \u20b9{target}."
            rtype = "watch"
        else:
            rec = f"AVOID. EMA {'bullish but weak RSI' if bull else 'bearish'}. Wait for trend reversal + RSI>45."
            rtype = "sell"
    else:
        return None

    if entry is None or sl is None or target is None:
        return None
    rr = round((target - entry) / (entry - sl), 1) if sl < entry else 0
    return {
        "symbol": symbol,
        "name": STOCK_NAMES.get(symbol, symbol),
        "source": source,
        "price": cp,
        "pct": pct,
        "strategy": strat,
        "entry": entry,
        "sl": sl,
        "target": target,
        "rr": rr,
        "signals": sigs,
        "rec": rec,
        "recType": rtype,
        "score": score,
        "holdPeriod": hold,
    }
