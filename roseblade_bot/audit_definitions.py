"""
EVA Assistant audit channel and event definitions.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChannelDefinition:
    key: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class EventDefinition:
    key: str
    title: str
    channel_key: str
    default_color: int
    emoji: str


CHANNEL_DEFINITIONS: dict[str, ChannelDefinition] = {
    "administration": ChannelDefinition(
        key="administration",
        name="администрация",
        description="Роли, права, административные изменения и действия staff.",
    ),
    "member_roles": ChannelDefinition(
        key="member_roles",
        name="выдача-ролей",
        description="Выдача и снятие ролей участникам сервера.",
    ),
    "moderation": ChannelDefinition(
        key="moderation",
        name="баны",
        description="Баны, кики, тайм-ауты и прочие наказания.",
    ),
    "movement": ChannelDefinition(
        key="movement",
        name="перемещения",
        description="Перемещения пользователей между голосовыми каналами и отключения модераторами.",
    ),
    "voice": ChannelDefinition(
        key="voice",
        name="войс",
        description="Входы, выходы и изменения голосового состояния.",
    ),
    "voice_moderation": ChannelDefinition(
        key="voice_moderation",
        name="войс-модерация",
        description="Серверные mute/deaf и другие модераторские действия в голосовых каналах.",
    ),
    "channels": ChannelDefinition(
        key="channels",
        name="каналы",
        description="Создание, удаление и обновление каналов.",
    ),
    "threads": ChannelDefinition(
        key="threads",
        name="ветки",
        description="Создание, удаление и обновление веток.",
    ),
    "messages": ChannelDefinition(
        key="messages",
        name="сообщения",
        description="Удаление и редактирование сообщений.",
    ),
    "members": ChannelDefinition(
        key="members",
        name="участники",
        description="Вход, выход, смена никнейма, роли и бусты.",
    ),
    "server": ChannelDefinition(
        key="server",
        name="сервер",
        description="Приглашения и общие изменения сервера.",
    ),
    "webhooks": ChannelDefinition(
        key="webhooks",
        name="вебхуки",
        description="Создание, удаление и изменение вебхуков.",
    ),
}


EVENT_DEFINITIONS: dict[str, EventDefinition] = {
    "member_banned": EventDefinition("member_banned", "Участник забанен", "moderation", 0xE74C3C, "🔨"),
    "member_unbanned": EventDefinition("member_unbanned", "Участник разбанен", "moderation", 0x2ECC71, "🔓"),
    "member_kicked": EventDefinition("member_kicked", "Участника выгнали", "moderation", 0xE67E22, "👢"),
    "member_timeout_applied": EventDefinition(
        "member_timeout_applied",
        "Тайм-аут выдан",
        "moderation",
        0xF1C40F,
        "⏳",
    ),
    "member_timeout_removed": EventDefinition(
        "member_timeout_removed",
        "Тайм-аут снят",
        "moderation",
        0x2ECC71,
        "⌛",
    ),
    "channel_created": EventDefinition("channel_created", "Канал создан", "channels", 0x3498DB, "📁"),
    "channel_deleted": EventDefinition("channel_deleted", "Канал удалён", "channels", 0xE74C3C, "🗑️"),
    "channel_updated": EventDefinition("channel_updated", "Канал обновлён", "channels", 0xF39C12, "🛠️"),
    "channel_permissions_updated": EventDefinition(
        "channel_permissions_updated",
        "Обновлены разрешения канала",
        "administration",
        0x9B59B6,
        "🔐",
    ),
    "thread_created": EventDefinition("thread_created", "Ветка создана", "threads", 0x3498DB, "🧵"),
    "thread_deleted": EventDefinition("thread_deleted", "Ветка удалена", "threads", 0xE74C3C, "🧵"),
    "thread_updated": EventDefinition("thread_updated", "Ветка обновлена", "threads", 0xF39C12, "🧵"),
    "role_created": EventDefinition("role_created", "Роль создана", "administration", 0x3498DB, "🎭"),
    "role_deleted": EventDefinition("role_deleted", "Роль удалена", "administration", 0xE74C3C, "🎭"),
    "role_updated": EventDefinition("role_updated", "Роль обновлена", "administration", 0xF39C12, "🎭"),
    "message_deleted": EventDefinition("message_deleted", "Следы зачищены", "messages", 0xE74C3C, "🗑️"),
    "message_edited": EventDefinition("message_edited", "Сообщение переписано", "messages", 0xF39C12, "✏️"),
    "member_joined": EventDefinition("member_joined", "Участник присоединился", "members", 0x2ECC71, "📥"),
    "member_left": EventDefinition("member_left", "Участник покинул сервер", "members", 0x95A5A6, "📤"),
    "nickname_changed": EventDefinition("nickname_changed", "Никнейм изменён", "members", 0x1ABC9C, "🪪"),
    "member_role_added": EventDefinition("member_role_added", "Роль накинута", "member_roles", 0x2ECC71, "➕"),
    "member_role_removed": EventDefinition("member_role_removed", "Роль снята", "member_roles", 0xE67E22, "➖"),
    "invite_created": EventDefinition("invite_created", "Приглашение создано", "server", 0x3498DB, "📨"),
    "invite_deleted": EventDefinition("invite_deleted", "Приглашение удалено", "server", 0xE74C3C, "📨"),
    "server_updated": EventDefinition("server_updated", "Изменения сервера", "server", 0x9B59B6, "🏰"),
    "server_boosted": EventDefinition("server_boosted", "Буст сервера", "server", 0xFF73A1, "🚀"),
    "webhook_created": EventDefinition("webhook_created", "Создание вебхука", "webhooks", 0x3498DB, "🪝"),
    "webhook_deleted": EventDefinition("webhook_deleted", "Удаление вебхука", "webhooks", 0xE74C3C, "🪝"),
    "webhook_updated": EventDefinition("webhook_updated", "Изменение вебхука", "webhooks", 0xF39C12, "🪝"),
    "member_voice_joined": EventDefinition("member_voice_joined", "Участник присоединился к войсу", "voice", 0x2ECC71, "🎙️"),
    "member_voice_left": EventDefinition("member_voice_left", "Участник покинул войс", "voice", 0x95A5A6, "🎙️"),
    "member_voice_switched": EventDefinition(
        "member_voice_switched",
        "Участник переключился между голосовыми каналами",
        "voice",
        0x3498DB,
        "🔀",
    ),
    "member_moved": EventDefinition(
        "member_moved",
        "Переезд по войсу",
        "movement",
        0x9B59B6,
        "↔️",
    ),
    "member_disconnected": EventDefinition(
        "member_disconnected",
        "Выгнали из войса",
        "movement",
        0xE67E22,
        "⛔",
    ),
    "member_voice_state_changed": EventDefinition(
        "member_voice_state_changed",
        "Движ в войсе",
        "voice",
        0x1ABC9C,
        "🎛️",
    ),
    "member_voice_moderation_changed": EventDefinition(
        "member_voice_moderation_changed",
        "Голосовая модерация",
        "voice_moderation",
        0xC0392B,
        "🔇",
    ),
}


EVENT_CHOICES = sorted(EVENT_DEFINITIONS)
