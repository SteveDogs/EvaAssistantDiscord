from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS watches (
                user_id INTEGER NOT NULL, symbol TEXT NOT NULL,
                PRIMARY KEY (user_id, symbol)
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, symbol TEXT NOT NULL,
                comparator TEXT NOT NULL, target REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        self.connection.commit()

    def get(self, key: str, default: str = "") -> str:
        row = self.connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.connection.commit()

    def get_prices(self) -> dict[str, float]:
        return json.loads(self.get("last_prices", "{}"))

    def set_prices(self, prices: dict[str, float]) -> None:
        self.set("last_prices", json.dumps(prices))

    def watch(self, user_id: int, symbols: list[str]) -> None:
        self.connection.execute("DELETE FROM watches WHERE user_id = ?", (user_id,))
        self.connection.executemany("INSERT INTO watches(user_id, symbol) VALUES(?, ?)", ((user_id, item) for item in symbols))
        self.connection.commit()

    def watches(self, user_id: int) -> list[str]:
        return [row["symbol"] for row in self.connection.execute("SELECT symbol FROM watches WHERE user_id = ?", (user_id,))]

    def add_alert(self, chat_id: int, user_id: int, symbol: str, comparator: str, target: float) -> None:
        self.connection.execute(
            "INSERT INTO alerts(chat_id, user_id, symbol, comparator, target) VALUES(?, ?, ?, ?, ?)",
            (chat_id, user_id, symbol, comparator, target),
        )
        self.connection.commit()

    def alerts(self, user_id: int) -> list[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM alerts WHERE user_id = ? AND enabled = 1 ORDER BY id", (user_id,)).fetchall()

    def active_alerts(self) -> list[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM alerts WHERE enabled = 1 ORDER BY id").fetchall()

    def complete_alert(self, alert_id: int) -> None:
        self.connection.execute("UPDATE alerts SET enabled = 0 WHERE id = ?", (alert_id,))
        self.connection.commit()
