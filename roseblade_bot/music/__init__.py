"""
EVA Assistant music package.
Copyright (c) 2026 Steve Dogs Studio.
"""

from roseblade_bot.music.lavalink_config import (
    LAVALINK_VERSION,
    LAVASRC_VERSION,
    YOUTUBE_PLUGIN_VERSION,
    render_lavalink_application_yml,
)
from roseblade_bot.music.service import (
    MusicAutocompleteSuggestion,
    MusicCommandError,
    MusicEnqueueResult,
    MusicService,
)

__all__ = (
    "LAVALINK_VERSION",
    "LAVASRC_VERSION",
    "YOUTUBE_PLUGIN_VERSION",
    "MusicAutocompleteSuggestion",
    "MusicCommandError",
    "MusicEnqueueResult",
    "MusicService",
    "render_lavalink_application_yml",
)
