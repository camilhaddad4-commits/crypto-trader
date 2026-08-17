"""Telegram trade notifications. Silently no-ops if credentials aren't set,
so local runs without .env and forks of the repo still work."""
import os
from pathlib import Path

import requests


def _load_dotenv() -> None:
    """Minimal .env loader so local runs get credentials without extra deps."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def send(text: str) -> None:
    if not TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass  # an alert failure must never break a trading cycle


def trade_alert(trade: dict, equity: float) -> None:
    emoji = {"buy": "🟢", "sell": "🔴"}.get(trade["side"], "⚪")
    reason = trade.get("note") or "manual"
    send(
        f"{emoji} <b>{trade['side'].upper()} {trade['symbol'].replace('_', '/')}</b>\n"
        f"${trade['usd']:,.2f} @ ${trade['price']:,.2f}\n"
        f"qty {trade['qty']:.6f}\n"
        f"reason: {reason}\n"
        f"equity now: ${equity:,.2f}"
    )
