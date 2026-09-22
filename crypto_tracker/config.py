from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env(path: Path) -> None:
    """Load a minimal .env file without adding another runtime dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    token: str
    channel_id: int
    interval_seconds: int
    currency: str
    symbols: dict[str, str]
    move_alert_percent: float
    alert_cooldown_minutes: int
    database_path: Path

    @classmethod
    def from_env(cls, base_dir: Path) -> "Settings":
        load_env(base_dir / ".env")
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        channel_id = os.getenv("CHANNEL_ID", "").strip()
        if not token or not channel_id:
            raise RuntimeError("TELEGRAM_BOT_TOKEN and CHANNEL_ID must be set in .env")

        raw_symbols = os.getenv(
            "TRACKED_COINS",
            "BTC:bitcoin,ETH:ethereum,TON:the-open-network,SOL:solana,NOT:notcoin,"
            "XRP:ripple,BNB:binancecoin,ADA:cardano,OKB:okb",
        )
        symbols: dict[str, str] = {}
        for item in raw_symbols.split(","):
            symbol, coin_id = item.split(":", 1)
            symbols[symbol.strip().upper()] = coin_id.strip()

        return cls(
            token=token,
            channel_id=int(channel_id),
            interval_seconds=max(60, int(os.getenv("UPDATE_INTERVAL_SECONDS", "180"))),
            currency=os.getenv("QUOTE_CURRENCY", "usd").lower(),
            symbols=symbols,
            move_alert_percent=float(os.getenv("MOVE_ALERT_PERCENT", "5")),
            alert_cooldown_minutes=max(5, int(os.getenv("ALERT_COOLDOWN_MINUTES", "30"))),
            database_path=base_dir / "data" / "tracker.sqlite3",
        )
