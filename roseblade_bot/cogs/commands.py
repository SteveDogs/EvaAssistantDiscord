"""
EVA Assistant slash-command cog.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from roseblade_bot.audit_cog_commands import AuditCogCommandsMixin
from roseblade_bot.audit_cog_runtime import AuditCogRuntimeMixin
from roseblade_bot.cogs.shared import EvaPassiveSharedCog


class EvaCommandsCog(EvaPassiveSharedCog, AuditCogCommandsMixin, AuditCogRuntimeMixin):
    """Administrative slash commands and manual maintenance actions."""

