"""Kraken public market data — no account or API keys required."""
import requests

API = "https://api.kraken.com/0/public"


def _kraken_pair(symbol: str) -> str:
    """'BTC/USD' -> 'XBTUSD' (Kraken calls Bitcoin XBT)."""
    return symbol.upper().replace("/", "").replace("BTC", "XBT")


def ticker(symbol: str = "BTC/USD") -> dict:
    """Return {'bid': float, 'ask': float, 'last': float} for a pair."""
    resp = requests.get(f"{API}/Ticker", params={"pair": _kraken_pair(symbol)}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data["error"]:
        raise SystemExit(f"Kraken error for {symbol}: {data['error']}")
    t = next(iter(data["result"].values()))
    return {"bid": float(t["b"][0]), "ask": float(t["a"][0]), "last": float(t["c"][0])}
