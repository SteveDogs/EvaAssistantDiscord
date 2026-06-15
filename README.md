# EVA Assistant

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.7%2B-5865F2?style=flat-square&logo=discord&logoColor=white)
![Статус](https://img.shields.io/badge/статус-активная%20разработка-111111?style=flat-square)
![Бренд](https://img.shields.io/badge/Steve%20Dogs-Studio-E84A5F?style=flat-square)

**EVA Assistant** — это Discord-бот для аудит-логов и модерации, созданный для серверов, которым нужны не сухие технические простыни, а аккуратные, читаемые и красиво оформленные логи.

Бот ориентирован на реальные задачи модерации:

- автоматически создаёт структуру аудит-каналов
- разносит события по отдельным логическим разделам
- показывает, кто именно выполнил действие и кого оно затронуло
- ведёт логи голосовой модерации и перемещений по войсам
- логирует удаление и редактирование сообщений
- поддерживает фирменный стиль и более живую подачу в embed-логах

## Зачем EVA

Большинство аудит-ботов для Discord страдают от одних и тех же проблем:

- слишком много мусорной технической информации
- сухие и роботизированные формулировки
- плохо читаемые embeds
- свалка всех событий в один канал

**EVA Assistant** делает упор на другое:

- читаемость в первую очередь
- понятное разделение логов по категориям
- удобство для администрации и модераторов
- аккуратный Discord-native UI/UX
- живой фирменный стиль вместо бездушного системного текста

## Возможности

### Автосоздание аудит-каналов

EVA умеет автоматически создать и поддерживать структуру логов с отдельными текстовыми каналами:

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

### Какие события логируются

- баны, разбаны, кики и тайм-ауты
- вход и выход участников
- смена никнейма
- бусты сервера
- выдача и снятие ролей у участников
- создание, изменение и удаление ролей
- создание, изменение и удаление каналов
- создание, изменение и удаление веток
- изменение прав канала
- удаление, массовое удаление и редактирование сообщений
- вход в войс, выход из войса и самостоятельное переключение между каналами
- модераторское перемещение и отключение участников из войса
- voice state и voice moderation события
- создание, изменение и удаление вебхуков
- создание и удаление приглашений
- общие изменения сервера

### Что видно в логах

EVA старается показывать только полезное:

- кто выполнил действие
- кого затронуло действие
- где это произошло
- что именно изменилось
- причину из Audit Log, если Discord её отдал

## Быстрый старт

### 1. Установка зависимостей

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Настройка окружения

Создай `.env` на основе `.env.example`.

Основные переменные:

```env
DISCORD_TOKEN=your_bot_token_here
GUILD_ID=123456789012345678
AUDIT_CATEGORY_NAME=Аудит
AUDIT_CATEGORY_ID=
STATE_FILE=data/audit_state.json
ENABLE_MEMBERS_INTENT=false
ENABLE_MESSAGE_CONTENT_INTENT=false
```

Если нужно складывать лог-каналы в уже существующую категорию Discord:

```env
AUDIT_CATEGORY_ID=123456789012345678
```

### 3. Запуск

```powershell
python main.py
```

## Права бота в Discord

Обязательные:

- `View Audit Log`
- `Manage Channels`
- `Read Messages / View Channels`
- `Read Message History`
- `Send Messages`
- `Embed Links`

Рекомендуемые:

- `Manage Roles`
- `Move Members`
- `Moderate Members`
- `Manage Messages`

## Privileged Intents

Для полного покрытия логов в Discord Developer Portal желательно включить:

- `Server Members Intent`
- `Message Content Intent`

После этого нужно отразить это в `.env`:

```env
ENABLE_MEMBERS_INTENT=true
ENABLE_MESSAGE_CONTENT_INTENT=true
```

Без этих intents EVA всё равно работает, но часть событий будет ограничена самим Discord.

## Slash-команды

- `/audit_setup` — создать и синхронизировать аудит-каналы
- `/audit_status` — показать текущую конфигурацию
- `/audit_events` — вывести список ключей событий
- `/audit_set_color` — задать цвет для конкретного события
- `/audit_toggle` — включить или выключить событие
- `/audit_bind` — привязать логическую группу к конкретному каналу
- `/audit_export` — выгрузить историю логов
- `/audit_ignore_channel`
- `/audit_unignore_channel`
- `/audit_ignore_category`
- `/audit_unignore_category`
- `/audit_ignore_user`
- `/audit_unignore_user`
- `/audit_ignore_role`
- `/audit_unignore_role`

## Структура проекта

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

## Брендинг

**EVA Assistant** — фирменный moderation/audit проект от **Steve Dogs Studio**.

- Сайт: [steve.dog](https://steve.dog)
- Telegram: [t.me/stevedog](https://t.me/stevedog)
- GitHub: [SteveDogs/EvaAssistantDiscord](https://github.com/SteveDogs/EvaAssistantDiscord)

## Дорожная карта

- стили поведения и настроения Евы
- более гибкие режимы тона логов
- улучшение выгрузки истории
- веб-панель или административный интерфейс
- дополнительные moderation и anti-spam фишки

## Копирайт

Copyright (c) 2026 Steve Dogs Studio.

В этом репозитории размещены исходный код, брендированные материалы и публичная витрина проекта EVA Assistant.
Если отдельный `LICENSE` не добавлен, все права по умолчанию остаются у автора.
