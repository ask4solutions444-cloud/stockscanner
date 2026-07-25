"""Aggregates market headlines from a handful of public Indian financial
news RSS feeds and scores each headline with simple keyword-based
sentiment (no paid news/sentiment API required).

RSS feed layouts occasionally change - each feed is fetched independently
and wrapped in try/except so one broken feed never takes down the others.
If a feed URL goes stale, swap it out below.
"""
import time
import feedparser

FEEDS = [
    {"name": "Economic Times Markets", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"},
    {"name": "Moneycontrol", "url": "https://www.moneycontrol.com/rss/latestnews.xml"},
    {"name": "Livemint Markets", "url": "https://www.livemint.com/rss/markets"},
    {"name": "Business Standard Markets", "url": "https://www.business-standard.com/rss/markets-106.rss"},
]

BULLISH_WORDS = [
    "rally", "rallies", "surge", "surges", "soar", "soars", "jump", "jumps", "gain", "gains",
    "gains ground", "record high", "all-time high", "upgrade", "outperform", "rebound",
    "rebounds", "buy rating", "bullish", "climbs", "advances", "recovers", "strong buy",
    "beats estimates", "wins order", "expansion", "profit rises", "upbeat",
]
BEARISH_WORDS = [
    "crash", "crashes", "plunge", "plunges", "tumble", "tumbles", "slump", "slumps", "falls",
    "fall", "sell-off", "selloff", "bearish", "downgrade", "underperform", "correction",
    "drops", "declines", "loss", "losses", "weak", "cuts guidance", "profit falls", "misses estimates",
    "recession", "inflation fears", "sell rating",
]

_CACHE = {"ts": 0, "data": None}
CACHE_TTL = 600  # 10 minutes


def _score_headline(title):
    t = title.lower()
    pos = sum(1 for w in BULLISH_WORDS if w in t)
    neg = sum(1 for w in BEARISH_WORDS if w in t)
    if pos > neg:
        return "bullish"
    if neg > pos:
        return "bearish"
    return "neutral"


def fetch_news(max_per_feed=8):
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < CACHE_TTL:
        return _CACHE["data"]

    headlines = []
    feed_errors = []
    for feed in FEEDS:
        try:
            parsed = feedparser.parse(feed["url"])
            if parsed.bozo and not parsed.entries:
                feed_errors.append(feed["name"])
                continue
            for entry in parsed.entries[:max_per_feed]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                headlines.append({
                    "source": feed["name"],
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "sentiment": _score_headline(title),
                })
        except Exception:
            feed_errors.append(feed["name"])

    bullish = sum(1 for h in headlines if h["sentiment"] == "bullish")
    bearish = sum(1 for h in headlines if h["sentiment"] == "bearish")
    neutral = sum(1 for h in headlines if h["sentiment"] == "neutral")
    total = len(headlines) or 1

    if bullish > bearish * 1.2:
        overall = "bullish"
    elif bearish > bullish * 1.2:
        overall = "bearish"
    else:
        overall = "mixed"

    result = {
        "headlines": headlines[:40],
        "counts": {"bullish": bullish, "bearish": bearish, "neutral": neutral},
        "bullishPct": round(bullish / total * 100, 1),
        "bearishPct": round(bearish / total * 100, 1),
        "overallSentiment": overall,
        "feedErrors": feed_errors,
    }
    _CACHE["ts"] = now
    _CACHE["data"] = result
    return result
