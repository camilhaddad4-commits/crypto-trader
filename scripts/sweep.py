"""SMA parameter sweep: test fast/slow combos across timeframes and symbols.

Reuses one candle fetch per (symbol, timeframe) so the API isn't hammered.
Prints top combos per market plus combos that hold up ACROSS markets — the
cross-market view matters most, single-market winners are usually curve-fit.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import cryptocom, strategy

FASTS = [5, 8, 10, 12, 15, 20, 25, 30]
SLOWS = [20, 30, 40, 50, 60, 80, 100, 150, 200]
MARKETS = [("BTC_USD", "1h"), ("BTC_USD", "4h"), ("BTC_USD", "1D"),
           ("ETH_USD", "4h"), ("ETH_USD", "1D")]

results = []
for symbol, tf in MARKETS:
    candles = cryptocom.candles(symbol, tf, 300)[:-1]
    hold = None
    for fast in FASTS:
        for slow in SLOWS:
            if fast >= slow or slow + 10 > len(candles):
                continue
            r = strategy.backtest(symbol, tf, fast=fast, slow=slow, candles=candles)
            hold = r["buy_and_hold_pct"]
            results.append({"symbol": symbol, "tf": tf, "fast": fast, "slow": slow,
                            "ret": r["return_pct"], "hold": hold, "trades": r["trades"]})
    print(f"fetched {symbol} {tf}: {len(candles)} candles, buy&hold {hold:+.1f}%")

print("\n=== top 5 per market (min 4 trades) ===")
for symbol, tf in MARKETS:
    rows = sorted([r for r in results if r["symbol"] == symbol and r["tf"] == tf and r["trades"] >= 4],
                  key=lambda r: -r["ret"])[:5]
    print(f"\n{symbol} {tf} (buy&hold {rows[0]['hold']:+.1f}%)" if rows else f"\n{symbol} {tf}: no combos with 4+ trades")
    for r in rows:
        print(f"  SMA {r['fast']:>2}/{r['slow']:<3} -> {r['ret']:+7.2f}%  ({r['trades']} trades)")

print("\n=== robust across markets: avg return, must beat 0% in 3+ of 5 markets ===")
combos = {}
for r in results:
    combos.setdefault((r["fast"], r["slow"]), []).append(r)
scored = []
for (fast, slow), rows in combos.items():
    if len(rows) < len(MARKETS):
        continue
    wins = sum(1 for r in rows if r["ret"] > 0)
    avg = sum(r["ret"] for r in rows) / len(rows)
    total_trades = sum(r["trades"] for r in rows)
    scored.append((avg, wins, fast, slow, total_trades))
for avg, wins, fast, slow, tt in sorted(scored, reverse=True)[:10]:
    flag = " <-- robust" if wins >= 3 else ""
    print(f"  SMA {fast:>2}/{slow:<3}  avg {avg:+6.2f}%  positive in {wins}/5 markets  ({tt} trades total){flag}")

current = [r for r in results if r["fast"] == strategy.FAST and r["slow"] == strategy.SLOW]
if current:
    avg = sum(r["ret"] for r in current) / len(current)
    print(f"\ncurrent SMA {strategy.FAST}/{strategy.SLOW}: avg {avg:+.2f}% across the 5 markets")
