"""SMA crossover strategy + backtester.

Signal: buy when the fast moving average crosses above the slow one, sell when
it crosses below. Dumb but honest — the point is discipline, not prophecy.
"""
from bot import cryptocom

FAST = 20
SLOW = 50
STOP_LOSS_PCT = 0.03    # exit any position 3% below entry, no questions asked
TAKE_PROFIT_PCT = 0.06  # bank the win 6% above entry — 2:1 reward-to-risk vs the stop


def sma(values: list[float], n: int) -> float:
    return sum(values[-n:]) / n


def signal(closes: list[float]) -> str:
    """'buy', 'sell', or 'hold' based on the last two candles' MA relationship."""
    if len(closes) < SLOW + 1:
        return "hold"
    fast_now, slow_now = sma(closes, FAST), sma(closes, SLOW)
    fast_prev, slow_prev = sma(closes[:-1], FAST), sma(closes[:-1], SLOW)
    if fast_prev <= slow_prev and fast_now > slow_now:
        return "buy"
    if fast_prev >= slow_prev and fast_now < slow_now:
        return "sell"
    return "hold"


def backtest(symbol: str = "BTC_USD", timeframe: str = "4h", count: int = 300,
             starting_cash: float = 100.0, fee_rate: float = 0.005) -> dict:
    """Replay the strategy over historical candles. All-in/all-out sizing."""
    candles = cryptocom.candles(symbol, timeframe, count)[:-1]  # last candle is still forming — drop it
    closes = [c["close"] for c in candles]
    cash, qty, entry, trades = starting_cash, 0.0, 0.0, []

    for i in range(SLOW + 1, len(closes)):
        price = closes[i]
        if qty > 0 and candles[i]["low"] <= entry * (1 - STOP_LOSS_PCT):
            stop_price = entry * (1 - STOP_LOSS_PCT)
            cash = qty * stop_price * (1 - fee_rate)
            trades.append(("stop", stop_price))
            qty = 0.0
            continue
        if qty > 0 and candles[i]["high"] >= entry * (1 + TAKE_PROFIT_PCT):
            tp_price = entry * (1 + TAKE_PROFIT_PCT)
            cash = qty * tp_price * (1 - fee_rate)
            trades.append(("tp", tp_price))
            qty = 0.0
            continue
        sig = signal(closes[: i + 1])
        if sig == "buy" and cash > 0:
            qty = (cash / price) * (1 - fee_rate)
            entry = price
            trades.append(("buy", price))
            cash = 0.0
        elif sig == "sell" and qty > 0:
            cash = qty * price * (1 - fee_rate)
            trades.append(("sell", price))
            qty = 0.0

    final = cash + qty * closes[-1]
    hold_final = starting_cash * (closes[SLOW + 1] and closes[-1] / closes[SLOW + 1])
    return {
        "symbol": symbol, "timeframe": timeframe, "candles": len(closes),
        "trades": len(trades), "start": starting_cash,
        "final": round(final, 2),
        "return_pct": round((final / starting_cash - 1) * 100, 2),
        "buy_and_hold_pct": round((hold_final / starting_cash - 1) * 100, 2),
    }
