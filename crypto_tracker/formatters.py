from __future__ import annotations

from datetime import datetime
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .provider import Coin


def money(value: float) -> str:
    if value >= 1000:
        return f"${value:,.2f}"
    if value >= 1:
        return f"${value:.2f}"
    if value >= 0.01:
        return f"${value:.4f}"
    return f"${value:.8f}"


def change(value: float | None) -> str:
    if value is None:
        return "⚪ н/д"
    mark = "🟢" if value > 0 else "🔴" if value < 0 else "⚪"
    return f"{mark} {value:+.2f}%"


def keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Обновить", callback_data="market:refresh"), InlineKeyboardButton("Топ дня", callback_data="market:top")],
        [InlineKeyboardButton("BTC", callback_data="coin:BTC"), InlineKeyboardButton("ETH", callback_data="coin:ETH"), InlineKeyboardButton("TON", callback_data="coin:TON")],
    ])


def dashboard(coins: list[Coin]) -> str:
    now = datetime.now().strftime("%d.%m %H:%M")
    lines = ["<b>Крипторынок сейчас</b>", "<blockquote>Котировки обновляются автоматически. Это информация, не финансовый совет.</blockquote>"]
    for coin in coins:
        lines.append(f"<b>{escape(coin.symbol)}</b>  {money(coin.price)}   {change(coin.change_24h)}")
    lines.extend(["", f"<i>Обновлено: {now}</i>"])
    return "\n".join(lines)


def coin_card(coin: Coin) -> str:
    market_cap = f"${coin.market_cap:,.0f}" if coin.market_cap else "н/д"
    volume = f"${coin.volume:,.0f}" if coin.volume else "н/д"
    return "\n".join([
        f"<b>{escape(coin.symbol)} · {escape(coin.name)}</b>", "",
        f"Цена: <b>{money(coin.price)}</b>",
        f"24 часа: {change(coin.change_24h)}",
        f"Капитализация: {market_cap}",
        f"Объём за 24ч: {volume}",
        "", "<i>Информация, не финансовый совет.</i>",
    ])


def move_alert(symbol: str, before: float, current: float, percent: float) -> str:
    direction = "вырос" if percent > 0 else "снизился"
    icon = "🚀" if percent > 0 else "⚠️"
    return f"{icon} <b>{escape(symbol)} заметно {direction}</b>\n\n{money(before)} → <b>{money(current)}</b>\nИзменение: {change(percent)}\n\n<i>Рынок шумит, решения принимайте спокойно.</i>"
