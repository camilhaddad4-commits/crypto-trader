"""3x leveraged paper sleeve — simulates Crypto.com perpetual futures honestly.

Separate $30 sleeve, separate state file. Models the costs spot doesn't have:
  - taker fee on NOTIONAL (margin x leverage), Crypto.com derivatives Lv1: 0.04%
  - funding payments (~0.01% per 8h on notional, the long-side norm)
  - liquidation: at 3x a ~-32% price move wipes the margin. Checked every cycle.
Hard rule: sleeve below $33 halts. No refills — the sleeve must earn its way back.
"""
import json
import time
from datetime import date
from pathlib import Path

from bot import cryptocom

STATE_FILE = Path(__file__).resolve().parent.parent / "lever_portfolio.json"

LEVERAGE = 3
STARTING_CASH = 100.0
FEE_RATE = 0.0004        # taker, charged on notional per side
FUNDING_8H = 0.0001      # 0.01% per 8h on notional while position open
MMR = 0.01               # maintenance margin rate (approximation)
HALT_FLOOR = 33.0        # sleeve equity below this: no new positions, ever
STOP_LOSS_PCT = 0.03     # -3% price = -9% margin (4h regime, sweep 2026-08-23)
TAKE_PROFIT_PCT = 0.06   # +6% price = +18% margin — 2:1 vs the stop
TIMEFRAME = "4h"         # sleeve trades 4h candles (perp fees make it viable; sweep 2026-08-23:
                         # SMA5/40 s3/t6 positive on BTC/ETH/SOL; spot stays on its proven daily)


def _load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"cash": STARTING_CASH, "position": None, "trades": [],
            "day": str(date.today()), "day_start_equity": STARTING_CASH}


def _save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _funding_owed(pos: dict, now_ts: float) -> float:
    hours = max(now_ts - pos["opened_ts"], 0) / 3600
    return pos["notional_entry"] * FUNDING_8H * (hours / 8)


def equity(state: dict | None = None) -> float:
    state = state or _load()
    total = state["cash"]
    pos = state["position"]
    if pos:
        bid = cryptocom.ticker(pos["symbol"])["bid"]
        upnl = pos["qty"] * (bid - pos["entry"])
        total += max(pos["margin"] + upnl - _funding_owed(pos, time.time()), 0)
    return total


def buy(symbol: str, note: str = "") -> dict:
    state = _load()
    if state["position"]:
        raise SystemExit("LEVER refused: sleeve already has a position.")
    eq = equity(state)
    if eq < HALT_FLOOR:
        raise SystemExit(f"LEVER halted: sleeve equity ${eq:.2f} below ${HALT_FLOOR} floor. No refills.")
    margin = state["cash"]
    ask = cryptocom.ticker(symbol)["ask"]
    notional = margin * LEVERAGE
    entry_fee = notional * FEE_RATE
    qty = notional / ask
    liq = ask * (1 - 1 / LEVERAGE + MMR)
    state["position"] = {"symbol": symbol, "margin": margin - entry_fee, "qty": qty,
                         "entry": ask, "notional_entry": notional, "liq": liq,
                         "opened_ts": time.time()}
    state["cash"] = 0.0
    trade = {"time": str(date.today()), "side": "buy", "symbol": symbol,
             "usd": round(margin, 2), "price": ask, "qty": qty,
             "note": f"{note} 3x liq={liq:,.0f}"}
    state["trades"].append(trade)
    _save(state)
    return trade


def close(reason: str, exit_price: float | None = None) -> dict:
    """Close the open position at bid (or a forced price for stop/liq fills)."""
    state = _load()
    pos = state["position"]
    if not pos:
        raise SystemExit("LEVER refused: no position to close.")
    price = exit_price if exit_price is not None else cryptocom.ticker(pos["symbol"])["bid"]
    pnl = pos["qty"] * (price - pos["entry"])
    exit_fee = pos["qty"] * price * FEE_RATE
    funding = _funding_owed(pos, time.time())
    proceeds = max(pos["margin"] + pnl - exit_fee - funding, 0.0)
    state["cash"] += proceeds
    trade = {"time": str(date.today()), "side": "sell", "symbol": pos["symbol"],
             "usd": round(proceeds, 2), "price": price, "qty": pos["qty"],
             "note": f"{reason} pnl={pnl:+.2f} funding={funding:.3f}"}
    state["trades"].append(trade)
    state["position"] = None
    _save(state)
    return trade


def check_exits(symbol: str) -> dict | None:
    """Liquidation first, then stop, then TP. Returns the closing trade or None."""
    state = _load()
    pos = state["position"]
    if not pos or pos["symbol"] != symbol:
        return None
    bid = cryptocom.ticker(symbol)["bid"]
    if bid <= pos["liq"]:
        return close("auto:LIQUIDATED", exit_price=pos["liq"])
    if bid <= pos["entry"] * (1 - STOP_LOSS_PCT):
        return close("auto:stop-loss-3x")
    if bid >= pos["entry"] * (1 + TAKE_PROFIT_PCT):
        return close("auto:take-profit-3x")
    return None


def has_position(symbol: str) -> bool:
    pos = _load()["position"]
    return bool(pos and pos["symbol"] == symbol)


def summary() -> dict:
    state = _load()
    return {"cash": state["cash"], "equity": equity(state),
            "position": state["position"], "trades": state["trades"]}
