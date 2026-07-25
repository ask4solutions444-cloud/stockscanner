"""Thin wrapper around the Upstox v2/v3 REST API.

Docs referenced:
  Auth:       https://upstox.com/developer/api-documentation/authentication/
  Get token:  POST https://api.upstox.com/v2/login/authorization/token
  Full quote: GET  https://api.upstox.com/v2/market-quote/quotes
  Historical: GET  https://api.upstox.com/v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}
  Instruments: https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz

Upstox access tokens expire daily (~3:30am IST) and there is no refresh-token
flow - a human has to complete the login dialog again each trading day. This
client stores whatever access token it currently has in memory and exposes
/login + /callback (wired up in app.py) so that re-authenticating is a single
click rather than a redeploy.
"""
import gzip
import io
import json
import os
import time
from datetime import date, timedelta

import requests

API_BASE = "https://api.upstox.com/v2"
API_BASE_V3 = "https://api.upstox.com/v3"
INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

# Well-known index instrument keys (not present in the NSE_EQ instrument file).
INDEX_KEYS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "SENSEX": "BSE_INDEX|SENSEX",
}


class UpstoxError(Exception):
    pass


class UpstoxClient:
    def __init__(self):
        self.api_key = os.environ.get("UPSTOX_API_KEY", "")
        self.api_secret = os.environ.get("UPSTOX_API_SECRET", "")
        self.redirect_uri = os.environ.get("UPSTOX_REDIRECT_URI", "")
        # Seed from env if the user has a fresh token; can be replaced at
        # runtime via the /callback OAuth flow.
        self.access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "") or None
        self.token_obtained_at = time.time() if self.access_token else None

        self._instrument_map = {}
        self._instrument_map_ts = 0

    # ── auth ────────────────────────────────────────────────────────
    def is_authenticated(self):
        return bool(self.access_token)

    def login_url(self):
        return (
            f"{API_BASE}/login/authorization/dialog"
            f"?response_type=code&client_id={self.api_key}&redirect_uri={self.redirect_uri}"
        )

    def exchange_code(self, code):
        resp = requests.post(
            f"{API_BASE}/login/authorization/token",
            data={
                "code": code,
                "client_id": self.api_key,
                "client_secret": self.api_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={
                "accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=15,
        )
        if not resp.ok:
            raise UpstoxError(f"Token exchange failed: {resp.status_code} {resp.text}")
        data = resp.json()
        self.access_token = data.get("access_token")
        self.token_obtained_at = time.time()
        return data

    def _headers(self):
        if not self.access_token:
            raise UpstoxError("Not authenticated - visit /login first")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    # ── instrument master ──────────────────────────────────────────
    def load_instruments(self, force=False):
        if self._instrument_map and not force and time.time() - self._instrument_map_ts < 12 * 3600:
            return self._instrument_map
        r = requests.get(INSTRUMENTS_URL, timeout=30)
        r.raise_for_status()
        raw = gzip.decompress(r.content)
        data = json.loads(raw)
        m = {}
        for row in data:
            if row.get("segment") == "NSE_EQ" and row.get("instrument_type") == "EQ":
                sym = (row.get("trading_symbol") or "").upper()
                key = row.get("instrument_key")
                if sym and key:
                    m[sym] = key
        self._instrument_map = m
        self._instrument_map_ts = time.time()
        return m

    def instrument_key(self, symbol):
        symbol = symbol.upper()
        if symbol in INDEX_KEYS:
            return INDEX_KEYS[symbol]
        m = self.load_instruments()
        return m.get(symbol)

    # ── market data ─────────────────────────────────────────────────
    def get_quotes(self, instrument_keys):
        """Full quotes (LTP, OHLC, volume, change) for up to 500 keys at once."""
        if not instrument_keys:
            return {}
        params = {"instrument_key": ",".join(instrument_keys)}
        r = requests.get(f"{API_BASE}/market-quote/quotes", headers=self._headers(), params=params, timeout=15)
        if not r.ok:
            raise UpstoxError(f"quotes failed: {r.status_code} {r.text}")
        return r.json().get("data", {})

    def get_daily_candles(self, instrument_key, days=400):
        """Daily OHLCV candles, oldest -> newest."""
        to_d = date.today()
        from_d = to_d - timedelta(days=days)
        url = f"{API_BASE_V3}/historical-candle/{instrument_key}/days/1/{to_d.isoformat()}/{from_d.isoformat()}"
        r = requests.get(url, headers=self._headers(), timeout=20)
        if not r.ok:
            raise UpstoxError(f"historical-candle failed: {r.status_code} {r.text}")
        candles = r.json().get("data", {}).get("candles", []) or []
        # Each candle: [timestamp, open, high, low, close, volume, oi] - newest first
        candles = list(reversed(candles))
        return candles

    def get_intraday_candles(self, instrument_key, unit="minutes", interval="30"):
        """Today's intraday candles (v3), oldest -> newest."""
        url = f"{API_BASE_V3}/historical-candle/intraday/{instrument_key}/{unit}/{interval}"
        r = requests.get(url, headers=self._headers(), timeout=20)
        if not r.ok:
            return []
        candles = r.json().get("data", {}).get("candles", []) or []
        return list(reversed(candles))


upstox = UpstoxClient()
