"""Alpaca paper-trading client wrapper with hard safety limits."""
import os

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoLatestQuoteRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from dotenv import load_dotenv

load_dotenv()

# Hard limits — the bot refuses orders beyond these no matter what.
MAX_ORDER_NOTIONAL_USD = 1_000   # max $ per single order
MAX_DAILY_LOSS_USD = 2_000       # stop trading if equity drops this much below last_equity


def trading_client() -> TradingClient:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY — copy .env.example to .env and fill it in.")
    # paper=True pins the client to the paper endpoint; live keys won't work here.
    return TradingClient(key, secret, paper=True)


def data_client() -> CryptoHistoricalDataClient:
    return CryptoHistoricalDataClient()  # crypto data needs no keys


def latest_quote(symbol: str = "BTC/USD"):
    req = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
    return data_client().get_crypto_latest_quote(req)[symbol]


def check_kill_switch(tc: TradingClient) -> None:
    acct = tc.get_account()
    drawdown = float(acct.last_equity) - float(acct.equity)
    if drawdown >= MAX_DAILY_LOSS_USD:
        raise SystemExit(
            f"KILL SWITCH: down ${drawdown:,.2f} today (limit ${MAX_DAILY_LOSS_USD:,}). No more orders."
        )


def place_market_order(symbol: str, side: str, notional_usd: float):
    if notional_usd > MAX_ORDER_NOTIONAL_USD:
        raise SystemExit(
            f"Refused: ${notional_usd:,.2f} exceeds per-order limit of ${MAX_ORDER_NOTIONAL_USD:,}."
        )
    tc = trading_client()
    check_kill_switch(tc)
    order = MarketOrderRequest(
        symbol=symbol,
        notional=round(notional_usd, 2),
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.GTC,
    )
    return tc.submit_order(order)
