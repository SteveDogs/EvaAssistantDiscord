"""Human-readable Discord role permission audits for EVA Assistant.

Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO

import discord


_PERMISSION_LABELS: tuple[tuple[str, str, str], ...] = (
    ("administrator", "Администратор", "critical"),
    ("manage_guild", "Управление сервером", "high"),
    ("manage_roles", "Управление ролями", "high"),
    ("manage_channels", "Управление каналами", "high"),
    ("manage_webhooks", "Управление вебхуками", "high"),
    ("view_audit_log", "Просмотр журнала аудита", "normal"),
    ("kick_members", "Выгонять участников", "high"),
    ("ban_members", "Банить участников", "high"),
    ("moderate_members", "Выдавать тайм-аут", "high"),
    ("manage_nicknames", "Управление никами", "normal"),
    ("manage_messages", "Управление сообщениями", "normal"),
    ("mention_everyone", "Упоминать @everyone/@here", "normal"),
    ("view_channel", "Просматривать каналы", "basic"),
    ("send_messages", "Отправлять сообщения", "basic"),
    ("send_messages_in_threads", "Писать в ветках", "basic"),
    ("embed_links", "Встраивать ссылки", "basic"),
    ("attach_files", "Прикреплять файлы", "basic"),
    ("read_message_history", "Читать историю", "basic"),
    ("add_reactions", "Ставить реакции", "basic"),
    ("connect", "Подключаться к войсу", "basic"),
    ("speak", "Говорить в войсе", "basic"),
    ("stream", "Стримить", "basic"),
    ("use_voice_activation", "Голосовая активность", "basic"),
    ("mute_members", "Отключать микрофон", "high"),
    ("deafen_members", "Отключать звук", "high"),
    ("move_members", "Перемещать участников", "high"),
)

_RISK_LABELS = {
    "critical": "КРИТИЧНО: полный доступ к серверу",
    "high": "ВНИМАНИЕ: сильное право управления",
}


@dataclass(frozen=True, slots=True)
class RoleAuditResult:
    embed: discord.Embed
    report: BytesIO
    role_count: int
    high_risk_count: int


def _role_permissions(role: discord.Role) -> list[tuple[str, str, str]]:
    return [
        (attribute, label, risk)
        for attribute, label, risk in _PERMISSION_LABELS
        if getattr(role.permissions, attribute, False)
    ]


def _channel_overwrites(guild: discord.Guild, role: discord.Role) -> list[str]:
    details: list[str] = []
    for channel in guild.channels:
        overwrite = channel.overwrites_for(role)
        allow, deny = overwrite.pair()
        if allow.value == 0 and deny.value == 0:
            continue
        granted = [label for attribute, label, _ in _PERMISSION_LABELS if getattr(allow, attribute, False)]
        denied = [label for attribute, label, _ in _PERMISSION_LABELS if getattr(deny, attribute, False)]
        parts: list[str] = []
        if granted:
            parts.append("разрешено: " + ", ".join(granted))
        if denied:
            parts.append("запрещено: " + ", ".join(denied))
        details.append(f"#{channel.name}: " + "; ".join(parts))
    return details


def _role_header(role: discord.Role) -> str:
    labels: list[str] = []
    if role.is_default():
        labels.append("базовая роль сервера")
    if role.managed:
        labels.append("интеграционная/системная роль")
    if not labels:
        labels.append("обычная роль")
    return ", ".join(labels)


def build_role_audit(guild: discord.Guild) -> RoleAuditResult:
    """Build a compact Discord embed plus a complete Markdown report."""
    ordered_roles = sorted(guild.roles, key=lambda role: role.position, reverse=True)
    high_risk_roles: list[tuple[discord.Role, list[str]]] = []
    lines = [
        f"# Аудит ролей: {guild.name}",
        "",
        "Отчёт показывает серверные права роли и прямые переопределения в каналах.",
        "Итоговые права конкретного человека могут отличаться: Discord складывает права всех его ролей.",
        "",
    ]

    for role in ordered_roles:
        permissions = _role_permissions(role)
        dangerous = [label for _, label, risk in permissions if risk in _RISK_LABELS]
        member_count = len(role.members)
        lines.extend(
            [
                f"## {role.position}. {role.name}",
                f"Тип: {_role_header(role)}.",
                f"Участников с ролью: {member_count}.",
            ]
        )
        if permissions:
            lines.append("Серверные права: " + ", ".join(label for _, label, _ in permissions) + ".")
        else:
            lines.append("Серверные права: специальных прав нет.")
        if dangerous:
            risk_notes = []
            if getattr(role.permissions, "administrator", False):
                risk_notes.append(_RISK_LABELS["critical"])
            if any(item for item in dangerous if item != "Администратор"):
                risk_notes.append("ВНИМАНИЕ: " + ", ".join(item for item in dangerous if item != "Администратор"))
            lines.append("Риски: " + " | ".join(risk_notes) + ".")
            high_risk_roles.append((role, dangerous))

        overwrites = _channel_overwrites(guild, role)
        if overwrites:
            lines.append(f"Переопределения каналов ({len(overwrites)}):")
            lines.extend(f"- {item}" for item in overwrites)
        else:
            lines.append("Переопределения каналов: нет.")
        lines.append("")

    report = BytesIO("\n".join(lines).encode("utf-8"))
    report.name = "eva-role-audit.md"

    risk_counter = Counter()
    for _, dangerous in high_risk_roles:
        for label in dangerous:
            risk_counter[label] += 1
    risk_summary = "\n".join(
        f"• <b>{label}</b>: {count}"
        for label, count in risk_counter.most_common(8)
    ) or "• Сильных прав в ролях не найдено."

    embed = discord.Embed(
        title="🛡️ Аудит ролей готов",
        description=(
            f"Ева просмотрела <b>{len(ordered_roles)}</b> ролей. "
            "Полная расшифровка прав и ограничений лежит в прикреплённом файле."
        ),
        color=discord.Color.gold() if high_risk_roles else discord.Color.green(),
    )
    embed.add_field(name="Роли с сильными правами", value=f"<b>{len(high_risk_roles)}</b>", inline=True)
    embed.add_field(name="Как читать отчёт", value="Сначала смотрите «Риски», затем ограничения отдельных каналов.", inline=True)
    embed.add_field(name="Найдено", value=risk_summary[:1024], inline=False)
    embed.set_footer(text="EVA Assistant • SteveDogs Studio • Права не изменялись")
    return RoleAuditResult(
        embed=embed,
        report=report,
        role_count=len(ordered_roles),
        high_risk_count=len(high_risk_roles),
    )
