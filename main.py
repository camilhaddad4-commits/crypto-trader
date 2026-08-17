"""Paper-trading bot on live Crypto.com Exchange prices. No account needed.

Usage:
  python main.py quote [SYMBOL]           # live bid/ask (default BTC_USD)
  python main.py account                  # fake-money equity, cash, P/L
  python main.py positions                # open paper positions
  python main.py buy SYMBOL DOLLARS       # e.g. buy BTC_USD 100
  python main.py sell SYMBOL [DOLLARS]    # omit dollars to close position
  python main.py trades                   # trade history
  python main.py backtest [SYMBOL] [TF]   # replay SMA strategy on history
  python main.py auto [SYMBOL] [MINUTES]  # run SMA strategy on a loop (paper)
  python main.py reset                    # wipe portfolio back to $100k
"""
import sys
import time
from datetime import datetime

from bot import cryptocom, paper, strategy

TRADE_SIZE_USD = 25  # what `auto` puts on each buy signal (25% of the $100 account)


def run_cycle(symbol: str) -> None:
    """One trading cycle: check stop-loss, then act on the SMA signal. Raises on failure."""
    now = datetime.now().strftime("%H:%M:%S")
    # last candle is still forming — drop it so signals can't repaint
    closes = [c["close"] for c in cryptocom.candles(symbol, "1h", 300)][:-1]
    sig = strategy.signal(closes)
    pos = paper.summary()["positions"].get(symbol)

    if pos:  # stop-loss first: protection outranks strategy
        entry = pos["cost"] / pos["qty"]
        bid = cryptocom.ticker(symbol)["bid"]
        if bid <= entry * (1 - strategy.STOP_LOSS_PCT):
            t = paper.sell(symbol, note=f"auto:stop-loss entry={entry:,.2f}")
            print(f"[{now}] STOP-LOSS sold {t['qty']:.6f} @ {t['price']:,.2f}")
            pos = None

    if sig == "buy" and not pos:
        t = paper.buy(symbol, TRADE_SIZE_USD, note="auto:sma-cross-up")
        print(f"[{now}] BUY  {t['qty']:.6f} @ {t['price']:,.2f}")
    elif sig == "sell" and pos:
        t = paper.sell(symbol, note="auto:sma-cross-down")
        print(f"[{now}] SELL {t['qty']:.6f} @ {t['price']:,.2f}")
    else:
        print(f"[{now}] hold (signal={sig}, position={bool(pos)}, last closed={closes[-1]:,.2f})")


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "help"

    if cmd == "quote":
        symbol = args[1] if len(args) > 1 else "BTC_USD"
        t = cryptocom.ticker(symbol)
        print(f"{symbol}  bid {t['bid']:,.2f}  ask {t['ask']:,.2f}")

    elif cmd == "account":
        s = paper.summary()
        print(f"equity  ${s['equity']:,.2f}")
        print(f"cash    ${s['cash']:,.2f}")
        print(f"P/L     ${s['pnl']:,.2f}")

    elif cmd == "positions":
        s = paper.summary()
        if not s["positions"]:
            print("no open positions")
        for sym, p in s["positions"].items():
            value = p["qty"] * cryptocom.ticker(sym)["bid"]
            print(f"{sym}  qty {p['qty']:.6f}  cost ${p['cost']:,.2f}  "
                  f"value ${value:,.2f}  P/L ${value - p['cost']:,.2f}")

    elif cmd == "buy":
        t = paper.buy(args[1], float(args[2]))
        print(f"bought {t['qty']:.6f} {t['symbol']} @ {t['price']:,.2f} (${t['usd']:,.2f})")

    elif cmd == "sell":
        usd = float(args[2]) if len(args) > 2 else None
        t = paper.sell(args[1], usd)
        print(f"sold {t['qty']:.6f} {t['symbol']} @ {t['price']:,.2f} (${t['usd']:,.2f})")

    elif cmd == "trades":
        for t in paper.summary()["trades"]:
            print(f"{t['time']}  {t['side']:4} {t['symbol']}  ${t['usd']:>10,.2f} @ {t['price']:,.2f}  {t['note']}")

    elif cmd == "backtest":
        symbol = args[1] if len(args) > 1 else "BTC_USD"
        tf = args[2] if len(args) > 2 else "4h"
        r = strategy.backtest(symbol, tf)
        print(f"{r['symbol']} {r['timeframe']} x{r['candles']} candles, {r['trades']} trades")
        print(f"strategy    {r['return_pct']:+.2f}%  (${r['start']:,.0f} -> ${r['final']:,.2f})")
        print(f"buy & hold  {r['buy_and_hold_pct']:+.2f}%")

    elif cmd == "auto":
        symbol = args[1] if len(args) > 1 else "BTC_USD"
        minutes = float(args[2]) if len(args) > 2 else 15
        print(f"auto-trading {symbol} every {minutes}m — SMA{strategy.FAST}/{strategy.SLOW} on closed 1h candles, "
              f"${TRADE_SIZE_USD}/trade, {strategy.STOP_LOSS_PCT:.0%} stop-loss, Ctrl+C to stop")
        failures = 0
        while True:
            try:
                run_cycle(symbol)
                failures = 0
            except KeyboardInterrupt:
                raise
            except SystemExit as e:
                # a refusal from the safety rails — the kill switch means stop for good
                print(f"HALTED: {e}")
                break
            except Exception as e:
                # network blips etc. must not kill the loop (gold bot Day 1 lesson)
                failures += 1
                print(f"ERROR ({failures} consecutive): {e} — retrying next cycle")
            time.sleep(minutes * 60)

    elif cmd == "auto-once":
        # single cycle for scheduled runners (GitHub Actions cron)
        symbol = args[1] if len(args) > 1 else "BTC_USD"
        try:
            run_cycle(symbol)
        except SystemExit as e:
            print(f"HALTED: {e}")  # exit 0: a safety-rail refusal is a valid outcome, not a CI failure

    elif cmd == "reset":
        paper.reset()
        print(f"portfolio reset to ${paper.STARTING_CASH:,.2f}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
