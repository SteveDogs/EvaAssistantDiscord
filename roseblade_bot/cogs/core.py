"""
EVA Assistant core runtime cog.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from roseblade_bot.audit_cog_runtime import AuditCogRuntimeMixin
from roseblade_bot.cogs.shared import EvaSharedCog


class EvaCoreCog(EvaSharedCog, AuditCogRuntimeMixin):
    """Boot lifecycle, background tasks and shared runtime helpers."""

