"""
EVA Assistant Lavalink configuration helpers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from roseblade_bot.config import MusicConfig

LAVALINK_VERSION = "4.2.1"
YOUTUBE_PLUGIN_VERSION = "1.18.1"
LAVASRC_VERSION = "4.8.3"


def _yaml_bool(value: bool) -> str:
    return "true" if value else "false"


def render_lavalink_application_yml(config: MusicConfig) -> str:
    spotify_enabled = bool(config.spotify_client_id and config.spotify_client_secret)
    spotify_block = (
        f"""    spotify:
      clientId: "{config.spotify_client_id}"
      clientSecret: "{config.spotify_client_secret}"
      countryCode: "{config.spotify_country_code}"
"""
        if spotify_enabled
        else """    spotify:
      # clientId: ""
      # clientSecret: ""
      countryCode: "US"
"""
    )

    return f"""# EVA Assistant Lavalink configuration.
# Copyright (c) 2026 Steve Dogs Studio / https://steve.dog
# Generated for ROSE BLADE music playback.

server:
  port: 2333
  address: 127.0.0.1

lavalink:
  plugins:
    - dependency: "dev.lavalink.youtube:youtube-plugin:{YOUTUBE_PLUGIN_VERSION}"
      repository: "https://maven.lavalink.dev/releases"
    - dependency: "com.github.topi314.lavasrc:lavasrc-plugin:{LAVASRC_VERSION}"
      repository: "https://maven.lavalink.dev/releases"

  server:
    password: "{config.lavalink_password}"
    sources:
      youtube: false
      bandcamp: true
      soundcloud: true
      twitch: true
      vimeo: true
      nico: true
      http: false
      local: false
    filters:
      volume: true
      equalizer: true
      karaoke: true
      timescale: true
      tremolo: true
      vibrato: true
      distortion: true
      rotation: true
      channelMix: true
      lowPass: true
    nonAllocatingFrameBuffer: false
    bufferDurationMs: 400
    frameBufferDurationMs: 5000
    opusEncodingQuality: 10
    resamplingQuality: LOW
    trackStuckThresholdMs: 10000

plugins:
  youtube:
    enabled: true
    allowSearch: true
    allowDirectVideoIds: true
    allowDirectPlaylistIds: true
    clients:
      - MUSIC
      - ANDROID_MUSIC
      - ANDROID_VR
      - MWEB
      - WEB
      - TVHTML5_SIMPLY
      - WEBEMBEDDED

  lavasrc:
    providers:
      - "ytmsearch:%QUERY%"
      - "ytsearch:%QUERY%"
    sources:
      spotify: {_yaml_bool(spotify_enabled)}
      applemusic: false
      deezer: false
      youtube: false
      ytdlp: false
{spotify_block}"""
