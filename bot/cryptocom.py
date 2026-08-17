"""Crypto.com Exchange public market data — no account or API keys required."""
import requests

API = "https://api.crypto.com/exchange/v1"


def ticker(symbol: str = "BTC_USD") -> dict:
    """Return {'bid': float, 'ask': float, 'last': float} for an instrument."""
    r = requests.get(f"{API}/public/get-tickers", params={"instrument_name": symbol}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0 or not data["result"]["data"]:
        raise SystemExit(f"Crypto.com error for {symbol}: {data}")
    t = data["result"]["data"][0]
    return {"bid": float(t["b"]), "ask": float(t["k"]), "last": float(t["a"])}


def candles(symbol: str = "BTC_USD", timeframe: str = "1h", count: int = 300) -> list[dict]:
    """Historical OHLCV candles, oldest first. Timeframes: 1m 5m 15m 30m 1h 4h 12h 1D 7D."""
    r = requests.get(
        f"{API}/public/get-candlestick",
        params={"instrument_name": symbol, "timeframe": timeframe, "count": count},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise SystemExit(f"Crypto.com error for {symbol}: {data}")
    return [
        {"t": c["t"], "open": float(c["o"]), "high": float(c["h"]),
         "low": float(c["l"]), "close": float(c["c"]), "volume": float(c["v"])}
        for c in data["result"]["data"]
    ]
