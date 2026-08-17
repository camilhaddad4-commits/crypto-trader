"""LIVE execution on Crypto.com Exchange — real money, same interface as paper.py.

Same safety rails as paper: $25 max order, one position at a time, daily-loss
kill switch (buys only — exits are always allowed). The exchange is the source
of truth for balances; portfolio.json stays the trade journal so the dashboard
keeps working unchanged.

Requires CRYPTO_API_KEY / CRYPTO_API_SECRET (env or .env). Never enable
withdrawal permission on the key.
"""
import hashlib
import hmac
import json
import time
from datetime import date
from pathlib import Path

import requests

from bot import cryptocom
from bot.notify import _load_dotenv
import os

_load_dotenv()
API_KEY = os.environ.get("CRYPTO_API_KEY", "").strip()
API_SECRET = os.environ.get("CRYPTO_API_SECRET", "").strip()
API = "https://api.crypto.com/exchange/v1"

STATE_FILE = Path(__file__).resolve().parent.parent / "portfolio.json"

STARTING_CASH = 100.0
MAX_ORDER_NOTIONAL = 25
MAX_DAILY_LOSS = 10
QTY_DECIMALS = 5          # BTC_USD min qty tick 0.00001


# ---------------------------------------------------------------- signing
def _params_to_str(obj, level=0):
    if level >= 3:
        return str(obj)
    out = ""
    for key in sorted(obj):
        out += key
        v = obj[key]
        if v is None:
            out += "null"
        elif isinstance(v, list):
            for sub in v:
                out += _params_to_str(sub, level + 1)
        else:
            out += str(v)
    return out


def _call(method: str, params: dict) -> dict:
    if not API_KEY or not API_SECRET:
        raise SystemExit("LIVE mode but CRYPTO_API_KEY / CRYPTO_API_SECRET not set.")
    req_id = int(time.time() * 1000)
    nonce = req_id
    payload = method + str(req_id) + API_KEY + _params_to_str(params) + str(nonce)
    sig = hmac.new(API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    body = {"id": req_id, "method": method, "api_key": API_KEY,
            "params": params, "nonce": nonce, "sig": sig}
    r = requests.post(f"{API}/{method}", json=body,
                      headers={"Content-Type": "application/json"}, timeout=15)
    data = r.json()
    if data.get("code") != 0:
        raise SystemExit(f"Crypto.com API error on {method}: code={data.get('code')} {data.get('message', '')}")
    return data.get("result", {})


# ---------------------------------------------------------------- state journal
def _load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"cash": STARTING_CASH, "positions": {}, "trades": [],
            "day": str(date.today()), "day_start_equity": STARTING_CASH}


def _save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------- balances
def _balances() -> dict:
    """Return {currency: available_qty} from the exchange."""
    result = _call("private/user-balance", {})
    out = {}
    for acct in result.get("data", []):
        for pos in acct.get("position_balances", []):
            out[pos["instrument_name"]] = float(pos["quantity"])
    return out


def equity(state: dict | None = None) -> float:
    bal = _balances()
    usd = bal.get("USD", 0.0)
    btc = bal.get("BTC", 0.0)
    if btc > 0:
        usd += btc * cryptocom.ticker("BTC_USD")["bid"]
    return usd


def _roll_day_and_check_kill_switch(state: dict) -> None:
    eq = equity()
    today = str(date.today())
    if state["day"] != today:
        state["day"] = today
        state["day_start_equity"] = eq
    loss = state["day_start_equity"] - eq
    if loss >= MAX_DAILY_LOSS:
        raise SystemExit(f"KILL SWITCH: down ${loss:,.2f} today (limit ${MAX_DAILY_LOSS:,}). No more orders.")


# ---------------------------------------------------------------- orders
def _wait_fill(order_id: str) -> dict:
    for _ in range(20):
        d = _call("private/get-order-detail", {"order_id": order_id})
        if d.get("status") == "FILLED":
            return d
        time.sleep(1)
    raise SystemExit(f"Order {order_id} not filled after 20s — check the exchange.")


def buy(symbol: str, usd: float, note: str = "") -> dict:
    if usd > MAX_ORDER_NOTIONAL:
        raise SystemExit(f"Refused: ${usd:,.2f} exceeds per-order cap of ${MAX_ORDER_NOTIONAL:,}.")
    state = _load()
    if state["positions"]:
        held = ", ".join(state["positions"])
        raise SystemExit(f"Refused: one bet at a time — close {held} before opening another.")
    _roll_day_and_check_kill_switch(state)
    result = _call("private/create-order", {
        "instrument_name": symbol, "side": "BUY", "type": "MARKET",
        "notional": f"{usd:.2f}",
    })
    d = _wait_fill(result["order_id"])
    price = float(d["avg_price"])
    qty = float(d["cumulative_quantity"])
    cost = float(d["cumulative_value"])
    state["positions"][symbol] = {"qty": qty, "cost": cost}
    state["cash"] = _balances().get("USD", 0.0)
    trade = {"time": str(date.today()), "side": "buy", "symbol": symbol,
             "usd": round(cost, 2), "price": price, "qty": qty, "note": note}
    state["trades"].append(trade)
    _save(state)
    return trade


def sell(symbol: str, usd: float | None = None, note: str = "") -> dict:
    """Sell the whole position (partial sells not used in live mode). Exits skip the kill switch."""
    state = _load()
    pos = state["positions"].get(symbol)
    if not pos or pos["qty"] <= 0:
        raise SystemExit(f"Refused: no {symbol} position to sell.")
    qty = round(min(pos["qty"], _balances().get("BTC", 0.0)), QTY_DECIMALS)
    if qty <= 0:
        raise SystemExit(f"Refused: exchange shows no BTC to sell (journal out of sync).")
    result = _call("private/create-order", {
        "instrument_name": symbol, "side": "SELL", "type": "MARKET",
        "quantity": f"{qty:.{QTY_DECIMALS}f}",
    })
    d = _wait_fill(result["order_id"])
    price = float(d["avg_price"])
    proceeds = float(d["cumulative_value"])
    state["positions"].pop(symbol, None)
    state["cash"] = _balances().get("USD", 0.0)
    trade = {"time": str(date.today()), "side": "sell", "symbol": symbol,
             "usd": round(proceeds, 2), "price": price, "qty": qty, "note": note}
    state["trades"].append(trade)
    _save(state)
    return trade


def summary() -> dict:
    state = _load()
    eq = equity(state)
    return {"cash": state["cash"], "equity": eq,
            "pnl": eq - STARTING_CASH, "positions": state["positions"],
            "trades": state["trades"]}


def reset() -> None:
    raise SystemExit("Refused: reset is a paper-mode command; live state belongs to the exchange.")
