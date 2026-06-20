"""
EVA Assistant event cog.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from roseblade_bot.audit_cog_events import AuditCogEventsMixin
from roseblade_bot.audit_cog_runtime import AuditCogRuntimeMixin
from roseblade_bot.cogs.shared import EvaPassiveSharedCog


class EvaEventsCog(EvaPassiveSharedCog, AuditCogEventsMixin, AuditCogRuntimeMixin):
    """Discord event listeners for audit, members, messages and voice."""

