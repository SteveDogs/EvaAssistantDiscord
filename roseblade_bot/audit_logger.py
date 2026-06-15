"""
EVA Assistant embed renderer and audit delivery service.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import random
from typing import Any

import discord

from roseblade_bot import EMBED_FOOTER
from roseblade_bot.audit_definitions import CHANNEL_DEFINITIONS, EVENT_DEFINITIONS
from roseblade_bot.storage import JsonStateStore


EmbedField = tuple[str, str, bool]

DEFAULT_EVA_LINES = (
    "Ева всё записала и пошла дальше держать сервер в тонусе.",
    "Сервер шумит, а Ева спокойно ведёт хронику.",
    "Я всё вижу. Иногда даже слишком многое.",
)

NO_REASON_LINES = (
    "Причину не оставили. Ева осуждающе молчит.",
    "Причина где-то потерялась по дороге. Классика.",
    "Без причины, зато с драмой. Сервер стабилен.",
)

FLAVOR_TEXTS: dict[str, tuple[str, ...]] = {
    "member_banned": (
        "Билет обратно пока не выписали.",
        "Бан-лист пополнился, атмосфера стала чуть спокойнее.",
        "Ева поставила печать и даже не удивилась.",
    ),
    "member_unbanned": (
        "Амнистия случилась, но второй раз лучше не проверять.",
        "Шлагбаум подняли, но взгляд Евы всё ещё настороженный.",
        "Возврат оформлен, интрига началась заново.",
    ),
    "member_kicked": (
        "Дверь нашлась подозрительно быстро.",
        "Выход показали без экскурсии по серверу.",
        "Ева записала кик с лёгким прищуром.",
    ),
    "member_timeout_applied": (
        "Небольшая пауза на подумать ещё никому не вредила.",
        "Чат отправил кого-то остывать.",
        "Ева перевернула песочные часы и кивнула.",
    ),
    "member_timeout_removed": (
        "Отсидка окончена, можно снова шевелить чат.",
        "Пауза закончилась, клавиатура снова в деле.",
        "Ева сняла ограничитель и сделала вид, что доверяет.",
    ),
    "channel_created": (
        "Ещё одна точка для контента, суеты и великих споров.",
        "Новый уголок сервера открыт официально.",
        "Ева уже ждёт, кто первым устроит там драму.",
    ),
    "channel_deleted": (
        "Архитектор с кувалдой снова в строю.",
        "Канал пал в бою с перестройкой.",
        "Ева моргнула, а канала уже нет.",
    ),
    "channel_updated": (
        "Косметика, хирургия или лёгкий хаос. Решайте сами.",
        "Канал переобули прямо на месте.",
        "Ева одобрительно склонила голову: стало интереснее.",
    ),
    "channel_permissions_updated": (
        "Кому можно, кому нельзя. Классика серверной жизни.",
        "Доступы снова нарезали как праздничный салат.",
        "Ева проверила списки и тихо хмыкнула.",
    ),
    "thread_created": (
        "Тред родился, спор официально узаконен.",
        "Ещё одна ветка для длинных мыслей и длиннее ссор.",
        "Ева приготовилась считать аргументы поштучно.",
    ),
    "thread_deleted": (
        "Дискуссию аккуратно прикопали.",
        "Ветку прикрыли, но осадочек остался.",
        "Ева поставила маленький крестик на этой истории.",
    ),
    "thread_updated": (
        "Тема переобулась прямо на ходу.",
        "Сюжет ветки слегка переписали.",
        "Ева заметила подмену декораций сразу.",
    ),
    "role_created": (
        "Ещё одна нашивка в коллекции сервера.",
        "Новая роль вышла в свет при полном параде.",
        "Ева уважает красивую иерархию. Иногда.",
    ),
    "role_deleted": (
        "Минус одна корона в обороте.",
        "Эта роль отправилась в музей былой славы.",
        "Ева записала утрату без траурной музыки.",
    ),
    "role_updated": (
        "Ливрею роли снова подкрутили.",
        "Роль сменила стиль, статус или настроение.",
        "Ева оценила апгрейд с лёгкой ухмылкой.",
    ),
    "message_deleted": (
        "Следы зачищены, но EVA всё равно всё заметила.",
        "Сообщение ушло в закат, а лог остался.",
        "Ева видела это. Теперь видите и вы.",
    ),
    "message_edited": (
        "Редактура подъехала. Старая версия нервно курит в сторонке.",
        "Сообщение переписали так, будто первой версии не было.",
        "Ева любит сравнивать черновик с финалом.",
    ),
    "member_joined": (
        "Новый герой появился на локации.",
        "Сервер пополнился ещё одной историей.",
        "Ева уже оценивает вайб новичка издалека.",
    ),
    "member_left": (
        "Тихий лив или эффектный уход. История умалчивает.",
        "Кто-то закрыл дверь снаружи, а Ева это отметила.",
        "Сервер стал чуть тише. Или это временно.",
    ),
    "nickname_changed": (
        "Ребрендинг личности завершён.",
        "Имя обновили, легенду оставили прежней.",
        "Ева делает вид, что не путается в этих ребрендингах.",
    ),
    "member_role_added": (
        "Новая нашивка пришита без наркоза.",
        "Кому-то выдали свежий статус и каплю ответственности.",
        "Ева отметила повышение в своей тетрадке.",
    ),
    "member_role_removed": (
        "Погоны сняты, атмосфера стала интереснее.",
        "Кого-то слегка облегчили по статусу.",
        "Ева записала разжалование особенно аккуратным почерком.",
    ),
    "invite_created": (
        "Дверь приоткрыли для новых лиц.",
        "Кого-то явно ждут в гости.",
        "Ева надеется, что зовут не в очередной хаос.",
    ),
    "invite_deleted": (
        "Вход временно прикрыли.",
        "Лишний пропуск убрали со стола.",
        "Ева любит, когда двери открывают с умом.",
    ),
    "server_updated": (
        "Кто-то крутил гайки прямо на проде.",
        "Серверу снова подкрутили характер.",
        "Ева слышит шорох конфига даже из соседнего канала.",
    ),
    "server_boosted": (
        "Серверу выдали витаминов и моральной поддержки.",
        "Буст залетел красиво, сервер расправил плечи.",
        "Ева уважает тех, кто приносит энергии в дом.",
    ),
    "webhook_created": (
        "Новый тихий автоматический житель поселился.",
        "Вебхук заехал без лишнего шума.",
        "Ева косится на автоматику, но пока терпит.",
    ),
    "webhook_deleted": (
        "Автоматику слегка укоротили.",
        "Один цифровой помощник отправился на покой.",
        "Ева проследила, чтобы он ушёл без драмы.",
    ),
    "webhook_updated": (
        "Вебхук сменил прическу и, возможно, характер.",
        "Автоматику переодели и снова пустили в люди.",
        "Ева не доверяет обновлённым вебхукам с первого взгляда.",
    ),
    "member_voice_joined": (
        "Залетел в войс и принёс атмосферу.",
        "Войс принял нового пассажира.",
        "Ева поправила гарнитуру и всё отметила.",
    ),
    "member_voice_left": (
        "Испарился из войса, как будто так и надо.",
        "Войс стал тише на один голос.",
        "Ева почти услышала хлопок двери.",
    ),
    "member_voice_switched": (
        "Переезд по комнатам прошёл без грузчиков.",
        "Кочевник войсов сменил локацию.",
        "Ева любит цивилизованную миграцию по каналам.",
    ),
    "member_moved": (
        "Такси по войсам снова работает без лицензии.",
        "Перетаскивание прошло бодро и без объявления остановок.",
        "Ева оценила технику манёвра.",
    ),
    "member_disconnected": (
        "Штекер вынули решительно и без сантиментов.",
        "Из войса вылетели без мягкой посадки.",
        "Ева записала это как жёсткую, но чистую работу.",
    ),
    "member_voice_state_changed": (
        "Кнопки в войсе пощёлкали, жизнь заиграла.",
        "Войс немного поменял настроение.",
        "Ева слышит даже нажатую кнопку mute.",
    ),
    "member_voice_moderation_changed": (
        "Голосовая дисциплина наведена, настроение проверяется.",
        "Войс-модерация щёлкнула по кнопкам и пошла дальше.",
        "Ева поставила галочку напротив слова 'контроль'.",
    ),
}

CASE_EVENT_KEYS = {
    "member_banned",
    "member_unbanned",
    "member_kicked",
    "member_timeout_applied",
    "member_timeout_removed",
    "member_moved",
    "member_disconnected",
    "member_voice_moderation_changed",
}

REASON_EVENT_KEYS = {
    "member_banned",
    "member_unbanned",
    "member_kicked",
    "member_timeout_applied",
    "member_timeout_removed",
    "member_role_added",
    "member_role_removed",
    "member_moved",
    "member_disconnected",
    "member_voice_moderation_changed",
}

IGNORED_CHANGE_ATTRS = {
    "flags",
    "overwrites",
    "permission_overwrites",
    "permissions",
    "exempt_channels",
    "exempt_roles",
    "applied_tags",
    "available_tags",
    "default_reaction_emoji",
    "emoji",
}

CHANGE_LABELS = {
    "name": "Название",
    "type": "Тип",
    "topic": "Тема",
    "category": "Категория",
    "slowmode_delay": "Медленный режим",
    "rate_limit_per_user": "Медленный режим",
    "nsfw": "NSFW",
    "position": "Позиция",
    "colour": "Цвет",
    "color": "Цвет",
    "hoist": "Показывать отдельно",
    "mentionable": "Можно упоминать",
    "nick": "Никнейм",
    "archived": "Архивирована",
    "locked": "Закрыта",
    "auto_archive_duration": "Автоархив",
    "default_auto_archive_duration": "Автоархив",
    "bitrate": "Битрейт",
    "user_limit": "Лимит участников",
    "code": "Код",
    "temporary": "Временное приглашение",
    "max_age": "Срок действия",
    "max_uses": "Лимит использований",
    "uses": "Использований",
    "description": "Описание",
    "preferred_locale": "Локаль",
    "afk_timeout": "AFK таймер",
    "communication_disabled_until": "Тайм-аут до",
    "mute": "Микрофон выключен",
    "deaf": "Звук выключен",
}


class AuditLogger:
    def __init__(
        self,
        *,
        store: JsonStateStore,
        default_category_name: str,
        default_category_id: int | None = None,
    ) -> None:
        self.store = store
        self.default_category_name = default_category_name
        self.default_category_id = default_category_id
        self._recent_events: dict[tuple[int, str, int], datetime] = {}
        self.history_path = store.path.parent / "audit_history.jsonl"

    def remember_recent(self, guild_id: int, event_key: str, target_id: int) -> None:
        self._recent_events[(guild_id, event_key, target_id)] = discord.utils.utcnow()

    def was_recent(self, guild_id: int, event_key: str, target_id: int, *, seconds: int = 10) -> bool:
        stamp = self._recent_events.get((guild_id, event_key, target_id))
        if stamp is None:
            return False
        return discord.utils.utcnow() - stamp <= timedelta(seconds=seconds)

    async def ensure_guild_setup(
        self,
        guild: discord.Guild,
        *,
        category_name: str | None = None,
        category_id: int | None = None,
    ) -> tuple[discord.CategoryChannel, dict[str, discord.TextChannel]]:
        saved = self.store.get_guild(guild.id)
        wanted_category_name = category_name or self.default_category_name
        wanted_category_id = category_id or self.default_category_id

        category = None
        if wanted_category_id:
            channel_by_id = guild.get_channel(wanted_category_id)
            if isinstance(channel_by_id, discord.CategoryChannel):
                category = channel_by_id

        if category is None:
            category = guild.get_channel(saved.get("category_id") or 0)
        if not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(guild.categories, name=wanted_category_name)

        if category is None:
            category = await guild.create_category(
                wanted_category_name,
                reason="Настройка аудит-логов RoseBladeBot",
            )

        created_channels: dict[str, discord.TextChannel] = {}
        persisted_channels: dict[str, int] = {}

        for key, definition in CHANNEL_DEFINITIONS.items():
            channel_id = saved["channels"].get(key)
            channel = guild.get_channel(channel_id or 0)
            if not isinstance(channel, discord.TextChannel):
                channel = discord.utils.get(category.text_channels, name=definition.name)

            if channel is None:
                channel = await guild.create_text_channel(
                    definition.name,
                    category=category,
                    topic=definition.description,
                    reason="Настройка аудит-логов RoseBladeBot",
                )
            elif channel.category_id != category.id:
                await channel.edit(
                    category=category,
                    reason="Синхронизация аудит-каналов RoseBladeBot",
                )

            created_channels[key] = channel
            persisted_channels[key] = channel.id

        self.store.update_guild(
            guild.id,
            category_id=category.id,
            channels=persisted_channels,
        )
        return category, created_channels

    async def get_channel_for_event(
        self,
        guild: discord.Guild,
        event_key: str,
    ) -> discord.TextChannel | None:
        event_definition = EVENT_DEFINITIONS[event_key]
        saved = self.store.get_guild(guild.id)
        channel_id = saved["channels"].get(event_definition.channel_key)
        channel = guild.get_channel(channel_id or 0)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    def color_for_event(self, guild_id: int, event_key: str) -> discord.Colour:
        saved = self.store.get_guild(guild_id)
        color_value = saved["colors"].get(event_key, EVENT_DEFINITIONS[event_key].default_color)
        return discord.Colour(color_value)

    @staticmethod
    def pick_flavor(event_key: str) -> str:
        return random.choice(FLAVOR_TEXTS.get(event_key, DEFAULT_EVA_LINES))

    @staticmethod
    def pick_missing_reason_line() -> str:
        return random.choice(NO_REASON_LINES)

    def should_log_event(
        self,
        guild: discord.Guild,
        event_key: str,
        *,
        related_channels: Sequence[discord.abc.GuildChannel | discord.Thread | None] | None = None,
        related_users: Sequence[discord.Member | discord.User | None] | None = None,
        related_roles: Sequence[discord.Role | None] | None = None,
    ) -> bool:
        if not self.store.is_event_enabled(guild.id, event_key):
            return False

        ignored_channel_ids = self.store.get_ignored_ids(guild.id, "channel_ids")
        ignored_category_ids = self.store.get_ignored_ids(guild.id, "category_ids")
        ignored_user_ids = self.store.get_ignored_ids(guild.id, "user_ids")
        ignored_role_ids = self.store.get_ignored_ids(guild.id, "role_ids")

        for channel in related_channels or ():
            if channel is None:
                continue
            if int(channel.id) in ignored_channel_ids:
                return False
            category_id = getattr(channel, "category_id", None)
            if category_id is not None and int(category_id) in ignored_category_ids:
                return False

        for user in related_users or ():
            if user is None:
                continue
            if int(user.id) in ignored_user_ids:
                return False

        for role in related_roles or ():
            if role is None:
                continue
            if int(role.id) in ignored_role_ids:
                return False

        return True

    async def send_event(
        self,
        guild: discord.Guild,
        event_key: str,
        description: str,
        *,
        actor: discord.abc.User | None = None,
        target: Any | None = None,
        reason: str | None = None,
        fields: Sequence[EmbedField] | None = None,
        show_actor_field: bool = False,
        show_target_field: bool = True,
        actor_label: str = "Исполнитель",
        target_label: str | None = None,
        thumbnail_target: Any | None = None,
        related_channels: Sequence[discord.abc.GuildChannel | discord.Thread | None] | None = None,
        related_users: Sequence[discord.Member | discord.User | None] | None = None,
        related_roles: Sequence[discord.Role | None] | None = None,
        include_case_id: bool | None = None,
        flavor_text: str | None = None,
    ) -> None:
        if not self.should_log_event(
            guild,
            event_key,
            related_channels=related_channels,
            related_users=related_users,
            related_roles=related_roles,
        ):
            return

        channel = await self.get_channel_for_event(guild, event_key)
        if channel is None:
            return

        definition = EVENT_DEFINITIONS[event_key]
        embed = discord.Embed(
            title=f"{definition.emoji} {definition.title}",
            description=description,
            colour=self.color_for_event(guild.id, event_key),
            timestamp=discord.utils.utcnow(),
        )

        if actor is not None:
            author_name = self.display_name(actor)
            author_icon = self.entity_image_url(actor)
            if author_icon:
                embed.set_author(name=author_name, icon_url=author_icon)
            else:
                embed.set_author(name=author_name)

        resolved_thumbnail = thumbnail_target if thumbnail_target is not None else target
        thumbnail_url = self.entity_image_url(resolved_thumbnail)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        if actor is not None and show_actor_field:
            embed.add_field(name=actor_label, value=self.format_entity(actor), inline=False)
        if target is not None and show_target_field:
            embed.add_field(
                name=target_label or self.label_for_entity(target),
                value=self.format_entity(target),
                inline=False,
            )
        if include_case_id is None:
            include_case_id = event_key in CASE_EVENT_KEYS
        if include_case_id:
            case_id = self.store.next_case_id(guild.id)
            embed.add_field(name="Кейс", value=f"`#{case_id}`", inline=True)
        if reason:
            embed.add_field(name="За что", value=self.shorten(reason, 1024), inline=False)
        elif actor is not None and event_key in REASON_EVENT_KEYS:
            embed.add_field(name="За что", value=self.pick_missing_reason_line(), inline=False)

        for name, value, inline in fields or ():
            embed.add_field(name=name, value=self.shorten(value, 1024), inline=inline)

        if flavor_text is None:
            flavor_text = self.pick_flavor(event_key)
        if flavor_text:
            embed.add_field(name="Ева шепчет", value=self.shorten(flavor_text, 1024), inline=False)

        footer_text = f"{guild.name} • {EMBED_FOOTER}"
        footer_icon = guild.icon.url if guild.icon else None
        embed.set_footer(text=footer_text, icon_url=footer_icon)
        await channel.send(embed=embed)
        self.append_history(
            guild=guild,
            event_key=event_key,
            description=description,
            actor=actor,
            target=target,
            channel=channel,
        )

    async def fetch_recent_audit_entry(
        self,
        guild: discord.Guild,
        *,
        actions: Iterable[discord.AuditLogAction],
        target_id: int | None = None,
        max_age_seconds: int = 15,
    ) -> discord.AuditLogEntry | None:
        deadline = discord.utils.utcnow() - timedelta(seconds=max_age_seconds)
        try:
            for action in actions:
                async for entry in guild.audit_logs(limit=6, action=action):
                    if entry.created_at < deadline:
                        break
                    candidate_target = getattr(entry.target, "id", None)
                    if target_id is not None and candidate_target != target_id:
                        continue
                    return entry
        except (discord.Forbidden, discord.HTTPException):
            return None

        return None

    @staticmethod
    def shorten(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    def append_history(
        self,
        *,
        guild: discord.Guild,
        event_key: str,
        description: str,
        actor: discord.abc.User | None,
        target: Any,
        channel: discord.TextChannel,
    ) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": discord.utils.utcnow().isoformat(),
            "guild_id": guild.id,
            "guild_name": guild.name,
            "event_key": event_key,
            "description": description,
            "actor_id": getattr(actor, "id", None),
            "actor_name": self.display_name(actor) if actor is not None else None,
            "target_id": getattr(target, "id", None),
            "target_name": self.display_name(target) if target is not None else None,
            "log_channel_id": channel.id,
            "log_channel_name": channel.name,
        }
        with self.history_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def export_history(self, guild_id: int, *, limit: int = 100) -> discord.File:
        entries: list[dict[str, Any]] = []
        if self.history_path.exists():
            for raw_line in self.history_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    item = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if item.get("guild_id") == guild_id:
                    entries.append(item)

        selected = entries[-limit:]
        buffer = io.BytesIO()
        buffer.write(json.dumps(selected, ensure_ascii=False, indent=2).encode("utf-8"))
        buffer.seek(0)
        return discord.File(buffer, filename=f"eva-audit-history-{guild_id}.json")

    @staticmethod
    def display_name(value: Any) -> str:
        if value is None:
            return "Неизвестно"
        if isinstance(value, (discord.Member, discord.User)):
            return value.display_name
        if isinstance(value, discord.Role):
            return value.name
        if isinstance(value, (discord.Thread, discord.abc.GuildChannel)):
            return getattr(value, "name", f"ID {value.id}")
        if isinstance(value, discord.Webhook):
            return value.name or f"Webhook {value.id}"
        if isinstance(value, discord.Invite):
            return value.code
        if isinstance(value, discord.Object):
            return f"ID {value.id}"
        return str(value)

    @staticmethod
    def entity_image_url(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (discord.Member, discord.User)):
            return value.display_avatar.url
        if isinstance(value, discord.Webhook) and value.avatar is not None:
            return value.avatar.url
        if isinstance(value, discord.Role) and isinstance(value.display_icon, discord.Asset):
            return value.display_icon.url
        return None

    @staticmethod
    def label_for_entity(value: Any) -> str:
        if isinstance(value, (discord.Member, discord.User)):
            return "Участник"
        if isinstance(value, discord.Role):
            return "Роль"
        if isinstance(value, discord.Thread):
            return "Ветка"
        if isinstance(value, discord.abc.GuildChannel):
            return "Канал"
        if isinstance(value, discord.Webhook):
            return "Вебхук"
        if isinstance(value, discord.Invite):
            return "Приглашение"
        return "Объект"

    @staticmethod
    def format_channel(channel: discord.abc.GuildChannel | discord.Thread | None, *, include_id: bool = False) -> str:
        if channel is None:
            return "Неизвестно"
        if hasattr(channel, "mention"):
            lines = [channel.mention]
            if include_id:
                lines.append(f"`{channel.id}`")
            return "\n".join(lines)
        return f"`{getattr(channel, 'name', 'unknown')}`"

    @staticmethod
    def format_channel_type(value: Any) -> str:
        mapping = {
            getattr(discord.ChannelType, "text", None): "Текстовый",
            getattr(discord.ChannelType, "voice", None): "Голосовой",
            getattr(discord.ChannelType, "category", None): "Категория",
            getattr(discord.ChannelType, "news", None): "Новостной",
            getattr(discord.ChannelType, "forum", None): "Форум",
            getattr(discord.ChannelType, "stage_voice", None): "Сцена",
            getattr(discord.ChannelType, "public_thread", None): "Публичная ветка",
            getattr(discord.ChannelType, "private_thread", None): "Приватная ветка",
            getattr(discord.ChannelType, "news_thread", None): "Новостная ветка",
        }
        return mapping.get(value, str(value))

    @staticmethod
    def format_change_value(value: Any) -> str:
        if value is None:
            return "Не задано"
        if isinstance(value, bool):
            return "Да" if value else "Нет"
        if isinstance(value, datetime):
            return discord.utils.format_dt(value, style="F")
        if isinstance(value, discord.ChannelType):
            return AuditLogger.format_channel_type(value)
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return value or "Пусто"
        if isinstance(value, list):
            return ", ".join(AuditLogger.format_change_value(item) for item in value) or "Нет"
        return AuditLogger.format_entity(value)

    @staticmethod
    def format_entity(value: Any, *, include_id: bool = False) -> str:
        if value is None:
            return "Неизвестно"

        if isinstance(value, (discord.Member, discord.User)):
            lines = [f"**{discord.utils.escape_markdown(value.display_name)}**", value.mention]
            username = str(value)
            if username != value.display_name:
                lines.insert(1, username)
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)

        if isinstance(value, discord.Role):
            lines = [f"**{value.name}**", value.mention]
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)

        if isinstance(value, discord.Thread):
            lines = [value.mention]
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)

        if isinstance(value, discord.abc.GuildChannel):
            return AuditLogger.format_channel(value, include_id=include_id)

        if isinstance(value, discord.Invite):
            channel_name = AuditLogger.format_channel(value.channel, include_id=include_id)
            return f"**{value.code}**\nКанал:\n{channel_name}"

        if isinstance(value, discord.Webhook):
            lines = [f"**{value.name or 'Webhook'}**"]
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)

        if isinstance(value, discord.Object):
            return f"`{value.id}`"

        if isinstance(value, list):
            return ", ".join(AuditLogger.format_entity(item, include_id=include_id) for item in value) or "Нет"

        if isinstance(value, bool):
            return "Да" if value else "Нет"

        if isinstance(value, discord.Asset):
            return value.url

        if isinstance(value, discord.Colour):
            return f"`#{value.value:06X}`"

        if isinstance(value, discord.ChannelType):
            return AuditLogger.format_channel_type(value)

        if isinstance(value, datetime):
            return discord.utils.format_dt(value, style="F")

        if isinstance(value, str):
            return value

        return f"`{value}`"

    def describe_changes(self, entry: discord.AuditLogEntry, *, limit: int = 8) -> str | None:
        changes: list[str] = []
        seen = 0

        try:
            for attr, after_value in entry.after:
                before_value = getattr(entry.before, attr, None)
                if before_value == after_value:
                    continue
                if attr in IGNORED_CHANGE_ATTRS:
                    continue
                changes.append(
                    f"**{CHANGE_LABELS.get(attr, attr)}**: {self.format_change_value(before_value)} → {self.format_change_value(after_value)}"
                )
                seen += 1
                if seen >= limit:
                    break
        except TypeError:
            return None

        return "\n".join(changes) if changes else None
