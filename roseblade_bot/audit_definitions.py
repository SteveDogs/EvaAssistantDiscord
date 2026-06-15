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
    "voice_sessions": ChannelDefinition(
        key="voice_sessions",
        name="войс-длительность",
        description="Сколько участники просидели в голосовых каналах и с кем именно.",
    ),
    "voice_moderation": ChannelDefinition(
        key="voice_moderation",
        name="войс-модерация",
        description="Серверные mute/deaf и другие модераторские действия в голосовых каналах.",
    ),
    "streams": ChannelDefinition(
        key="streams",
        name="стримы",
        description="Запуски и остановки стримов и камер в голосовых каналах.",
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
    "events": ChannelDefinition(
        key="events",
        name="события",
        description="Stage, запланированные события и прочие серверные активности.",
    ),
    "expressions": ChannelDefinition(
        key="expressions",
        name="эмодзи-стикеры",
        description="Эмодзи, стикеры и декоративные элементы сервера.",
    ),
    "soundboard": ChannelDefinition(
        key="soundboard",
        name="саунд-панель",
        description="Создание, удаление и настройка звуков саунд-панели.",
    ),
    "automod": ChannelDefinition(
        key="automod",
        name="автомод",
        description="Правила автомода и срабатывания автоматической модерации.",
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
    "members_pruned": EventDefinition("members_pruned", "Массовая чистка участников", "moderation", 0xE67E22, "🧹"),
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
    "message_pinned": EventDefinition("message_pinned", "Сообщение закреплено", "messages", 0xF1C40F, "📌"),
    "message_unpinned": EventDefinition("message_unpinned", "Сообщение откреплено", "messages", 0x95A5A6, "📍"),
    "member_joined": EventDefinition("member_joined", "Участник присоединился", "members", 0x2ECC71, "📥"),
    "member_left": EventDefinition("member_left", "Участник покинул сервер", "members", 0x95A5A6, "📤"),
    "nickname_changed": EventDefinition("nickname_changed", "Никнейм изменён", "members", 0x1ABC9C, "🪪"),
    "member_role_added": EventDefinition("member_role_added", "Роль накинута", "member_roles", 0x2ECC71, "➕"),
    "member_role_removed": EventDefinition("member_role_removed", "Роль снята", "member_roles", 0xE67E22, "➖"),
    "bot_added": EventDefinition("bot_added", "Бот добавлен", "administration", 0x3498DB, "🤖"),
    "invite_created": EventDefinition("invite_created", "Приглашение создано", "server", 0x3498DB, "📨"),
    "invite_updated": EventDefinition("invite_updated", "Приглашение обновлено", "server", 0xF39C12, "📨"),
    "invite_deleted": EventDefinition("invite_deleted", "Приглашение удалено", "server", 0xE74C3C, "📨"),
    "server_updated": EventDefinition("server_updated", "Изменения сервера", "server", 0x9B59B6, "🏰"),
    "server_boosted": EventDefinition("server_boosted", "Буст сервера", "server", 0xFF73A1, "🚀"),
    "emoji_created": EventDefinition("emoji_created", "Эмодзи создан", "expressions", 0x3498DB, "😀"),
    "emoji_updated": EventDefinition("emoji_updated", "Эмодзи обновлён", "expressions", 0xF39C12, "😀"),
    "emoji_deleted": EventDefinition("emoji_deleted", "Эмодзи удалён", "expressions", 0xE74C3C, "😀"),
    "sticker_created": EventDefinition("sticker_created", "Стикер создан", "expressions", 0x3498DB, "🖼️"),
    "sticker_updated": EventDefinition("sticker_updated", "Стикер обновлён", "expressions", 0xF39C12, "🖼️"),
    "sticker_deleted": EventDefinition("sticker_deleted", "Стикер удалён", "expressions", 0xE74C3C, "🖼️"),
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
    "member_voice_session_finished": EventDefinition(
        "member_voice_session_finished",
        "Сессия в войсе завершена",
        "voice_sessions",
        0x16A085,
        "⏱️",
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
    "member_stream_started": EventDefinition("member_stream_started", "Стрим запущен", "streams", 0xE91E63, "📺"),
    "member_stream_stopped": EventDefinition("member_stream_stopped", "Стрим остановлен", "streams", 0x95A5A6, "📺"),
    "member_camera_started": EventDefinition("member_camera_started", "Камера включена", "streams", 0x3498DB, "📷"),
    "member_camera_stopped": EventDefinition("member_camera_stopped", "Камера выключена", "streams", 0x95A5A6, "📷"),
    "member_voice_moderation_changed": EventDefinition(
        "member_voice_moderation_changed",
        "Голосовая модерация",
        "voice_moderation",
        0xC0392B,
        "🔇",
    ),
    "stage_instance_created": EventDefinition("stage_instance_created", "Сцена создана", "events", 0x3498DB, "🎭"),
    "stage_instance_updated": EventDefinition("stage_instance_updated", "Сцена обновлена", "events", 0xF39C12, "🎭"),
    "stage_instance_deleted": EventDefinition("stage_instance_deleted", "Сцена удалена", "events", 0xE74C3C, "🎭"),
    "scheduled_event_created": EventDefinition("scheduled_event_created", "Событие создано", "events", 0x3498DB, "🗓️"),
    "scheduled_event_updated": EventDefinition("scheduled_event_updated", "Событие обновлено", "events", 0xF39C12, "🗓️"),
    "scheduled_event_deleted": EventDefinition("scheduled_event_deleted", "Событие отменено", "events", 0xE74C3C, "🗓️"),
    "soundboard_sound_created": EventDefinition(
        "soundboard_sound_created",
        "Звук саунд-панели создан",
        "soundboard",
        0x3498DB,
        "🔊",
    ),
    "soundboard_sound_updated": EventDefinition(
        "soundboard_sound_updated",
        "Звук саунд-панели обновлён",
        "soundboard",
        0xF39C12,
        "🔊",
    ),
    "soundboard_sound_deleted": EventDefinition(
        "soundboard_sound_deleted",
        "Звук саунд-панели удалён",
        "soundboard",
        0xE74C3C,
        "🔊",
    ),
    "automod_rule_created": EventDefinition("automod_rule_created", "Правило автомода создано", "automod", 0x3498DB, "🛡️"),
    "automod_rule_updated": EventDefinition("automod_rule_updated", "Правило автомода обновлено", "automod", 0xF39C12, "🛡️"),
    "automod_rule_deleted": EventDefinition("automod_rule_deleted", "Правило автомода удалено", "automod", 0xE74C3C, "🛡️"),
    "automod_action_blocked": EventDefinition(
        "automod_action_blocked",
        "Автомод заблокировал сообщение",
        "automod",
        0xE67E22,
        "⛔",
    ),
    "automod_action_flagged": EventDefinition(
        "automod_action_flagged",
        "Автомод поднял флаг",
        "automod",
        0xF1C40F,
        "🚩",
    ),
    "automod_action_timeout": EventDefinition(
        "automod_action_timeout",
        "Автомод выдал тайм-аут",
        "automod",
        0xE74C3C,
        "⏱️",
    ),
    "automod_action_quarantined": EventDefinition(
        "automod_action_quarantined",
        "Автомод ограничил взаимодействия",
        "automod",
        0x8E44AD,
        "🚫",
    ),
}


EVENT_CHOICES = sorted(EVENT_DEFINITIONS)
