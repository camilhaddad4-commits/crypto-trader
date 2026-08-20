"""High-impact economic event calendar — the news blackout guard.

No NEW entries within BLACKOUT_HOURS of a listed event (spot and lever alike).
Exits, stops, and TPs are never blocked — protection always runs.

Times are UTC. Maintained by hand: verify/extend monthly (BLS releases 12:30 UTC,
FOMC decisions 18:00 UTC). An empty/stale calendar simply means no blackout.
"""
from datetime import datetime, timedelta, timezone

BLACKOUT_HOURS = 3

EVENTS = [
    ("PCE inflation", "2026-08-28T12:30:00"),
    ("Jobs report (NFP)", "2026-09-04T12:30:00"),
    ("CPI inflation", "2026-09-10T12:30:00"),
    ("PPI inflation", "2026-09-11T12:30:00"),
    ("FOMC rate decision", "2026-09-16T18:00:00"),
    ("Jobs report (NFP)", "2026-10-02T12:30:00"),
    ("CPI inflation", "2026-10-13T12:30:00"),
    ("FOMC rate decision", "2026-10-28T18:00:00"),
]


def active_blackout(now: datetime | None = None) -> str | None:
    """Return the event name if we're inside a blackout window, else None."""
    now = now or datetime.now(timezone.utc)
    window = timedelta(hours=BLACKOUT_HOURS)
    for name, iso in EVENTS:
        t = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
        if abs(now - t) <= window:
            return f"{name} at {t:%b %d %H:%M} UTC"
    return None
