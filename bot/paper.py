"""Local paper-trading engine: fake balance, real Crypto.com prices.

State lives in portfolio.json next to main.py. Later, a live.py module with the
same buy/sell/equity interface replaces this for real trading.
"""
import json
from datetime import date
from pathlib import Path

from bot import cryptocom

STATE_FILE = Path(__file__).resolve().parent.parent / "portfolio.json"

STARTING_CASH = 100.0        # realistic: what the live account will actually start with
FEE_RATE = 0.005             # 0.50% per fill — Crypto.com Lv1 spot taker fee (market orders pay taker)
MAX_ORDER_NOTIONAL = 100     # hard cap per order (user upgraded from $25, 2026-08-19)
MAX_DAILY_LOSS = 10          # kill switch: no new orders once down $10 (10%) on the day
SINGLE_POSITION = True       # one open bet at a time, ever


def _load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"cash": STARTING_CASH, "positions": {}, "trades": [],
            "day": str(date.today()), "day_start_equity": STARTING_CASH}


def _save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def equity(state: dict | None = None) -> float:
    state = state or _load()
    total = state["cash"]
    for sym, pos in state["positions"].items():
        total += pos["qty"] * cryptocom.ticker(sym)["bid"]
    return total


def _roll_day_and_check_kill_switch(state: dict) -> None:
    eq = equity(state)
    today = str(date.today())
    if state["day"] != today:
        state["day"] = today
        state["day_start_equity"] = eq
    loss = state["day_start_equity"] - eq
    if loss >= MAX_DAILY_LOSS:
        raise SystemExit(f"KILL SWITCH: down ${loss:,.2f} today (limit ${MAX_DAILY_LOSS:,}). No more orders.")


def buy(symbol: str, usd: float, note: str = "") -> dict:
    if usd > MAX_ORDER_NOTIONAL:
        raise SystemExit(f"Refused: ${usd:,.2f} exceeds per-order cap of ${MAX_ORDER_NOTIONAL:,}.")
    state = _load()
    _roll_day_and_check_kill_switch(state)
    if usd > state["cash"]:
        raise SystemExit(f"Refused: only ${state['cash']:,.2f} cash available.")
    if SINGLE_POSITION and state["positions"]:
        held = ", ".join(state["positions"])
        raise SystemExit(f"Refused: one bet at a time — close {held} before opening another.")
    price = cryptocom.ticker(symbol)["ask"]
    qty = (usd / price) * (1 - FEE_RATE)
    pos = state["positions"].get(symbol, {"qty": 0.0, "cost": 0.0})
    state["positions"][symbol] = {"qty": pos["qty"] + qty, "cost": pos["cost"] + usd}
    state["cash"] -= usd
    trade = {"time": str(date.today()), "side": "buy", "symbol": symbol,
             "usd": round(usd, 2), "price": price, "qty": qty, "note": note}
    state["trades"].append(trade)
    _save(state)
    return trade


def sell(symbol: str, usd: float | None = None, note: str = "") -> dict:
    """Sell $usd worth at bid, or the whole position if usd is None.

    No kill-switch check here: exits reduce risk and must always be allowed,
    even (especially) on a bad day. The kill switch only gates new buys.
    """
    state = _load()
    pos = state["positions"].get(symbol)
    if not pos or pos["qty"] <= 0:
        raise SystemExit(f"Refused: no {symbol} position to sell.")
    price = cryptocom.ticker(symbol)["bid"]
    qty = pos["qty"] if usd is None else min(usd / price, pos["qty"])
    proceeds = qty * price * (1 - FEE_RATE)
    remaining = pos["qty"] - qty
    if remaining * price < 1:  # dust — close it out
        state["positions"].pop(symbol)
    else:
        cost_removed = pos["cost"] * (qty / pos["qty"])
        state["positions"][symbol] = {"qty": remaining, "cost": pos["cost"] - cost_removed}
    state["cash"] += proceeds
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
    _save({"cash": STARTING_CASH, "positions": {}, "trades": [],
           "day": str(date.today()), "day_start_equity": STARTING_CASH})
