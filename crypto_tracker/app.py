from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .charts import render_chart
from .config import Settings
from .formatters import change, coin_card, dashboard, keyboard, money, move_alert
from .provider import Coin, CoinGeckoProvider
from .storage import Storage

BASE_DIR = Path(__file__).resolve().parent.parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("crypto_tracker")


class Tracker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = Storage(settings.database_path)
        self.provider = CoinGeckoProvider(settings.symbols, settings.currency)
        self.lock = asyncio.Lock()

    async def fetch(self) -> list[Coin]:
        return await self.provider.markets()

    async def update_dashboard(self, bot, announce_moves: bool = True) -> list[Coin]:
        async with self.lock:
            coins = await self.fetch()
            text = dashboard(coins)
            message_id = self.storage.get("dashboard_message_id")
            try:
                if message_id:
                    await bot.edit_message_text(text, chat_id=self.settings.channel_id, message_id=int(message_id), parse_mode=ParseMode.HTML, reply_markup=keyboard())
                else:
                    message = await bot.send_message(self.settings.channel_id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard())
                    self.storage.set("dashboard_message_id", str(message.message_id))
                    try:
                        await bot.pin_chat_message(self.settings.channel_id, message.message_id, disable_notification=True)
                    except Exception:
                        logger.info("Bot cannot pin the dashboard message in this channel")
            except Exception as exc:
                logger.warning("Dashboard edit failed; creating a new dashboard: %s", exc)
                message = await bot.send_message(self.settings.channel_id, text, parse_mode=ParseMode.HTML, reply_markup=keyboard())
                self.storage.set("dashboard_message_id", str(message.message_id))

            previous = self.storage.get_prices()
            current = {coin.symbol: coin.price for coin in coins}
            if announce_moves and previous:
                cooldown_key = "last_move_alert"
                last_alert = float(self.storage.get(cooldown_key, "0"))
                now = asyncio.get_running_loop().time()
                if now - last_alert >= self.settings.alert_cooldown_minutes * 60:
                    moves = []
                    for coin in coins:
                        before = previous.get(coin.symbol)
                        if before:
                            percent = (coin.price - before) / before * 100
                            if abs(percent) >= self.settings.move_alert_percent:
                                moves.append((abs(percent), coin, before, percent))
                    if moves:
                        _, coin, before, percent = max(moves, key=lambda item: item[0])
                        await bot.send_message(self.settings.channel_id, move_alert(coin.symbol, before, coin.price, percent), parse_mode=ParseMode.HTML)
                        self.storage.set(cooldown_key, str(now))
            by_symbol = {coin.symbol: coin for coin in coins}
            for alert in self.storage.active_alerts():
                coin = by_symbol.get(alert["symbol"])
                if not coin:
                    continue
                reached = coin.price >= alert["target"] if alert["comparator"] == ">" else coin.price <= alert["target"]
                if reached:
                    await bot.send_message(
                        alert["chat_id"],
                        f"🔔 <b>Личный алерт сработал</b>\n\n<b>{coin.symbol}</b>: {money(coin.price)}\nЦель: {alert['comparator']} ${alert['target']:,.2f}",
                        parse_mode=ParseMode.HTML,
                    )
                    self.storage.complete_alert(alert["id"])
            self.storage.set_prices(current)
            return coins


async def periodic(context: ContextTypes.DEFAULT_TYPE) -> None:
    tracker: Tracker = context.application.bot_data["tracker"]
    try:
        await tracker.update_dashboard(context.bot)
    except Exception:
        logger.exception("Periodic market update failed")


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tracker: Tracker = context.application.bot_data["tracker"]
    coins = await tracker.fetch()
    await update.effective_message.reply_html(dashboard(coins), reply_markup=keyboard())


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tracker: Tracker = context.application.bot_data["tracker"]
    if not context.args:
        await update.effective_message.reply_text("Напиши символ: /price BTC")
        return
    symbol = context.args[0].upper()
    coin = next((item for item in await tracker.fetch() if item.symbol == symbol), None)
    await update.effective_message.reply_html(coin_card(coin) if coin else f"Не нашла <b>{symbol}</b> в отслеживаемом списке.")


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tracker: Tracker = context.application.bot_data["tracker"]
    symbol = (context.args[0].upper() if context.args else "BTC")
    coin_id = tracker.settings.symbols.get(symbol)
    if not coin_id:
        await update.effective_message.reply_text("Напиши один из отслеживаемых символов, например: /chart TON")
        return
    chart = render_chart(symbol, await tracker.provider.chart(coin_id))
    await update.effective_message.reply_photo(chart, caption=f"<b>{symbol}</b> за последние 24 часа", parse_mode=ParseMode.HTML)


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tracker: Tracker = context.application.bot_data["tracker"]
    user_id = update.effective_user.id
    if not context.args:
        watches = tracker.storage.watches(user_id)
        await update.effective_message.reply_text("Твой список: " + (", ".join(watches) if watches else "пусто") + "\nПример: /watch BTC TON SOL")
        return
    symbols = [item.upper() for item in context.args if item.upper() in tracker.settings.symbols]
    tracker.storage.watch(user_id, symbols)
    await update.effective_message.reply_text("Список сохранён: " + (", ".join(symbols) if symbols else "пусто"))


async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tracker: Tracker = context.application.bot_data["tracker"]
    if len(context.args) != 3 or context.args[0].upper() not in tracker.settings.symbols or context.args[1] not in {">", "<"}:
        await update.effective_message.reply_text("Пример: /alert BTC > 100000\nПоказать свои: /alerts")
        return
    try:
        target = float(context.args[2].replace(",", "."))
    except ValueError:
        await update.effective_message.reply_text("Цена должна быть числом.")
        return
    tracker.storage.add_alert(update.effective_chat.id, update.effective_user.id, context.args[0].upper(), context.args[1], target)
    await update.effective_message.reply_text(f"Алерт сохранён: {context.args[0].upper()} {context.args[1]} ${target:,.2f}")


async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tracker: Tracker = context.application.bot_data["tracker"]
    alerts = tracker.storage.alerts(update.effective_user.id)
    text = "\n".join(f"#{item['id']} {item['symbol']} {item['comparator']} ${item['target']:,.2f}" for item in alerts) or "Активных личных алертов пока нет."
    await update.effective_message.reply_text(text)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Обновляю рынок…")
    tracker: Tracker = context.application.bot_data["tracker"]
    data = query.data
    coins = await tracker.fetch()
    if data == "market:top":
        ordered = sorted(coins, key=lambda coin: coin.change_24h or 0, reverse=True)
        text = "<b>Топ дня</b>\n\n" + "\n".join(f"<b>{coin.symbol}</b>  {change(coin.change_24h)}" for coin in ordered)
    elif data.startswith("coin:"):
        symbol = data.split(":", 1)[1]
        coin = next((item for item in coins if item.symbol == symbol), None)
        text = coin_card(coin) if coin else "Монета недоступна."
    else:
        text = dashboard(coins)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard())


async def post_init(application: Application) -> None:
    tracker: Tracker = application.bot_data["tracker"]
    application.job_queue.run_repeating(periodic, interval=tracker.settings.interval_seconds, first=5, name="market-dashboard")


async def post_shutdown(application: Application) -> None:
    await application.bot_data["tracker"].provider.close()


def main() -> None:
    settings = Settings.from_env(BASE_DIR)
    tracker = Tracker(settings)
    application = Application.builder().token(settings.token).post_init(post_init).post_shutdown(post_shutdown).build()
    application.bot_data["tracker"] = tracker
    application.add_handler(CommandHandler("market", market_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("chart", chart_command))
    application.add_handler(CommandHandler("watch", watch_command))
    application.add_handler(CommandHandler("alert", alert_command))
    application.add_handler(CommandHandler("alerts", alerts_command))
    application.add_handler(CallbackQueryHandler(callback))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
