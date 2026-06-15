# EVA Assistant

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.7%2B-5865F2?style=flat-square&logo=discord&logoColor=white)
![Status](https://img.shields.io/badge/status-active%20development-111111?style=flat-square)
![Brand](https://img.shields.io/badge/Steve%20Dogs-Studio-E84A5F?style=flat-square)

EVA Assistant is a Discord audit and moderation logging bot designed for communities that want readable, stylish, category-based server logs instead of raw technical noise.

Built for real moderation workflows:

- clean audit channels created automatically
- voice moderation and member movement tracking
- readable message delete and edit logs
- role assignment logging in a dedicated channel
- branded embed styling with a custom personality layer
- slash-command based setup and administration

## Why EVA

Most audit bots dump too much junk into embeds: IDs everywhere, dry phrasing, and barely readable event cards.

EVA Assistant focuses on:

- human-readable logs first
- moderator identity and target visibility
- structured channels by event family
- better Discord-native UX through embeds
- branded tone instead of robotic system text

## Feature Set

### Audit channels

EVA can automatically create and maintain a structured logging category with separate channels for:

- `администрация`
- `выдача-ролей`
- `баны`
- `перемещения`
- `войс`
- `войс-модерация`
- `каналы`
- `ветки`
- `сообщения`
- `участники`
- `сервер`
- `вебхуки`

### Logged events

- bans, unbans, kicks, and timeouts
- member join, leave, nickname changes, and boosts
- role assignment and role removal for members
- role create, update, and delete
- channel create, update, delete, and permission changes
- thread create, update, and delete
- message delete, bulk delete, and edit events
- voice join, leave, self-state changes, moves, disconnects, and voice moderation
- invite create and delete
- webhook create, update, and delete
- guild-level setting changes

### Moderation UX

EVA tries to show:

- who performed the action
- who was affected
- where it happened
- what actually changed
- the audit reason when Discord provides it

## Quick Start

### 1. Install dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure environment

Create `.env` from `.env.example`.

Key values:

```env
DISCORD_TOKEN=your_bot_token_here
GUILD_ID=123456789012345678
AUDIT_CATEGORY_NAME=Аудит
AUDIT_CATEGORY_ID=
STATE_FILE=data/audit_state.json
ENABLE_MEMBERS_INTENT=false
ENABLE_MESSAGE_CONTENT_INTENT=false
```

If you want logs to be created inside an existing Discord category, fill in:

```env
AUDIT_CATEGORY_ID=123456789012345678
```

### 3. Run the bot

```powershell
python main.py
```

## Required Discord Permissions

- `View Audit Log`
- `Manage Channels`
- `Read Messages / View Channels`
- `Read Message History`
- `Send Messages`
- `Embed Links`

Depending on how you use EVA, these are also recommended:

- `Manage Roles`
- `Move Members`
- `Moderate Members`
- `Manage Messages`

## Privileged Intents

For full coverage in Discord Developer Portal, enable:

- `Server Members Intent`
- `Message Content Intent`

Then mirror that in `.env`:

```env
ENABLE_MEMBERS_INTENT=true
ENABLE_MESSAGE_CONTENT_INTENT=true
```

Without these intents, EVA still works in a reduced mode, but some logs may be limited by Discord itself.

## Slash Commands

- `/audit_setup` - create and sync audit channels
- `/audit_status` - show current guild audit configuration
- `/audit_events` - list event keys
- `/audit_set_color` - set a custom color for an event
- `/audit_toggle` - enable or disable a specific event
- `/audit_bind` - bind a log group to a specific text channel
- `/audit_export` - export recent audit history
- `/audit_ignore_channel`
- `/audit_unignore_channel`
- `/audit_ignore_category`
- `/audit_unignore_category`
- `/audit_ignore_user`
- `/audit_unignore_user`
- `/audit_ignore_role`
- `/audit_unignore_role`

## Project Structure

```text
main.py
roseblade_bot/
  __init__.py
  audit_definitions.py
  audit_logger.py
  bot.py
  config.py
  storage.py
.env.example
requirements.txt
```

## Branding

EVA Assistant is a branded moderation utility by Steve Dogs Studio.

- Website: [steve.dog](https://steve.dog)
- Telegram: [t.me/stevedog](https://t.me/stevedog)
- Repository: [SteveDogs/EvaAssistantDiscord](https://github.com/SteveDogs/EvaAssistantDiscord)

## Roadmap

- audit style presets for different server vibes
- richer moderation reason handling
- export improvements
- optional dashboard / web control panel
- deeper anti-spam and moderation utilities

## Copyright

Copyright (c) 2026 Steve Dogs Studio.

This repository includes branded source code and public project materials for EVA Assistant.
If a separate `LICENSE` file is not present, all rights remain with the author by default.
