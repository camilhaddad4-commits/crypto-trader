# Crypto Paper Trader

Paper-trading bot on live Crypto.com Exchange prices. Fake $100 (mirroring the real
starting balance), real market data, no account or API keys needed. Built to swap in
real Crypto.com Exchange execution later.

## Commands

```
.venv\Scripts\python main.py quote               # live BTC_USD bid/ask
.venv\Scripts\python main.py account             # equity, cash, P/L
.venv\Scripts\python main.py buy BTC_USD 100     # paper market buy $100
.venv\Scripts\python main.py sell BTC_USD        # close the position
.venv\Scripts\python main.py positions
.venv\Scripts\python main.py trades
.venv\Scripts\python main.py backtest BTC_USD 4h # replay SMA strategy on history
.venv\Scripts\python main.py auto BTC_USD 15     # run strategy loop, checks every 15 min
.venv\Scripts\python main.py reset               # back to $100k
```

## Layout

- `bot/cryptocom.py` — public market data (tickers, candles)
- `bot/paper.py` — simulated fills, portfolio state in `portfolio.json`, safety rails
- `bot/strategy.py` — SMA 20/50 crossover signal + backtester
- `main.py` — CLI
- `bot/client.py`, `bot/kraken.py` — leftovers from earlier Alpaca/Kraken exploration, unused

## Safety rails (bot/paper.py)

- $25 max per order — 25% of the account (`MAX_ORDER_NOTIONAL`)
- One open position at a time (`SINGLE_POSITION`)
- Kill switch: refuses orders once down $10 on the day (`MAX_DAILY_LOSS`)
- 0.50% simulated fee per fill — Crypto.com Lv1 spot taker rate (`FEE_RATE`)

## Going live (later)

Write `bot/live.py` with the same `buy`/`sell`/`summary` interface using signed
Crypto.com Exchange API calls (key + HMAC secret from exchange settings, withdrawal
permission OFF), and point `main.py` at it. Nothing else changes.
