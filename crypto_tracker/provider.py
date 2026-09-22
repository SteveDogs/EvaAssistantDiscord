from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Coin:
    symbol: str
    name: str
    price: float
    change_24h: float | None
    market_cap: float | None
    volume: float | None


class CoinGeckoProvider:
    base_url = "https://api.coingecko.com/api/v3"

    def __init__(self, symbols: dict[str, str], currency: str) -> None:
        self.symbols = symbols
        self.currency = currency
        self._client = httpx.AsyncClient(timeout=15, headers={"Accept": "application/json"})

    async def close(self) -> None:
        await self._client.aclose()

    async def markets(self) -> list[Coin]:
        response = await self._client.get(
            f"{self.base_url}/coins/markets",
            params={
                "vs_currency": self.currency,
                "ids": ",".join(self.symbols.values()),
                "price_change_percentage": "24h,7d",
                "sparkline": "false",
            },
        )
        response.raise_for_status()
        by_id = {item["id"]: item for item in response.json()}
        result: list[Coin] = []
        for symbol, coin_id in self.symbols.items():
            item = by_id.get(coin_id)
            if not item:
                continue
            result.append(Coin(symbol, item["name"], float(item["current_price"]), item.get("price_change_percentage_24h_in_currency"), item.get("market_cap"), item.get("total_volume")))
        return result

    async def chart(self, coin_id: str, days: int = 1) -> list[tuple[float, float]]:
        response = await self._client.get(f"{self.base_url}/coins/{coin_id}/market_chart", params={"vs_currency": self.currency, "days": days})
        response.raise_for_status()
        return [(point[0] / 1000, float(point[1])) for point in response.json().get("prices", [])]
