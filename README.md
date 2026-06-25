# EVA Assistant

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.7%2B-5865F2?style=flat-square&logo=discord&logoColor=white)
![Статус](https://img.shields.io/badge/статус-активная%20разработка-111111?style=flat-square)
![Бренд](https://img.shields.io/badge/Steve%20Dogs-Studio-E84A5F?style=flat-square)
![Лицензия](https://img.shields.io/badge/license-Apache%202.0%20%2B%20NOTICE-2A9D8F?style=flat-square)

**EVA Assistant** — это Discord-бот для аудит-логов и модерации, созданный для серверов, которым нужны не сухие технические простыни, а аккуратные, читаемые и красиво оформленные логи.

Бот ориентирован на реальные задачи модерации:

- автоматически создаёт структуру аудит-каналов
- разносит события по отдельным логическим разделам
- показывает, кто именно выполнил действие и кого оно затронуло
- ведёт логи голосовой модерации и перемещений по войсам
- отдельно ведёт стримы, камеры, soundboard и automod
- логирует удаление и редактирование сообщений
- умеет автоматически ставить префиксы в ники по ролям
- умеет иногда кокетливо троллить мат в чате вместо тупого наказания
- умеет публиковать вечерний Steam-дайджест по расписанию
- умеет обновлять live-баннер сервера с онлайном, войсом и boost-уровнем
- умеет работать как музыкальный бот через Lavalink, YouTube Music и Spotify mirror
- умеет работать с официальным API `alerts.in.ua` для карт и событий повітряних тривог
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
- `войс-длительность`
- `войс-модерация`
- `стримы`
- `каналы`
- `ветки`
- `сообщения`
- `участники`
- `сервер`
- `события`
- `эмодзи-стикеры`
- `саунд-панель`
- `автомод`
- `вебхуки`

### Вечерний Steam-дайджест

EVA умеет раз в день публиковать небольшой Steam-дайджест в указанный канал.

Что входит в пост:

- статус Steam Web API и время ответа
- скидка дня из Steam Store
- уикенд-витрина Steam и free weekend / weekend deal, если Steam их подсвечивает
- маленькая сводка по Steam Support
- отдельная заметка по PUBG
- топ игр Steam по текущему онлайну

Для теста без ожидания вечера есть slash-команда:

- `/steam_digest_now`

### Живой баннер сервера

EVA умеет обновлять баннер Discord-сервера по расписанию и рисовать поверх него живую статистику:

- участников сервера
- онлайн прямо сейчас
- людей в voice/stage
- boost level и число бустов

Под это есть отдельная slash-команда для ручного прогона:

- `/server_banner_now`

### Повітряні тривоги через alerts.in.ua

EVA умеет работать с официальным API [`alerts.in.ua`](https://devs.alerts.in.ua/) и обновлять отдельный тревожный канал без парсинга Telegram.

Текущий продуманный сценарий такой:

- `alerts.in.ua` даёт фактическое состояние тревоги и карту
- `war_monitor` используется как слой живых уточнений про тип угрозы: БпЛА, балістика, МіГ-31К, КАБ и так далее
- карта в канале живёт одной заменяемой карточкой, а не копится стопкой
- отдельные уведомления приходят только на смену состояния или на реально новый живой сигнал, чтобы не спамить канал

Что бот уже забирает оттуда:

- текущий статус тревоги по всем областям
- список активных тревог с типом угрозы
- время начала тревоги
- область, район и конкретную локацию, если API её отдаёт
- тип угрозы: `air_raid`, `artillery_shelling`, `urban_fights`, `chemical`, `nuclear`

Что ещё можно брать по этому же токену, если захотим развить EVA дальше:

- статус по конкретному `UID` области, района или города
- полный статус по всем `UID` Украины для более детальной районной логики
- историю тревог по региону за `month_ago`

Важно:

- у `alerts.in.ua` мягкий лимит примерно `8-10` запросов в минуту с одного IP
- у истории отдельный лимит: `2` запроса в минуту
- токен нельзя хранить в публичном фронте или сливать в репозиторий
- для экономии лимита EVA использует кеширование через `If-Modified-Since`

Для ручной проверки карты есть slash-команда:

- `/air_alert_now`

### Музыкальный режим EVA

EVA умеет работать как отдельный музыкальный слой, не смешиваясь с аудитом и модерацией.

Что уже умеет:

- подключаться в голосовой канал и держать отдельный Lavalink player
- искать треки по `YouTube Music` по умолчанию
- падать на `YouTube` как на fallback, если `YouTube Music` не дал результата
- принимать `YouTube`, `YouTube Music` и `Spotify` ссылки
- вести очередь, паузу, скип, громкость и авто-выход по idle timeout
- красиво анонсировать старт следующего трека в текстовый канал

Команды:

- `/music_status`
- `/music_join`
- `/music_play`
- `/music_now`
- `/music_queue`
- `/music_skip`
- `/music_pause`
- `/music_resume`
- `/music_stop`
- `/music_volume`
- `/music_shuffle`
- `/music_leave`

Важно:

- `Spotify` здесь работает как mirror-источник: EVA берёт метаданные Spotify и ищет playable-вариант через YouTube Music / YouTube
- без `MUSIC_SPOTIFY_CLIENT_ID` и `MUSIC_SPOTIFY_CLIENT_SECRET` YouTube Music будет работать, а Spotify-ссылки останутся выключены

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
- длительность голосовой сессии до выхода или перехода в другой канал
- модераторское перемещение и отключение участников из войса
- voice state и voice moderation события
- создание, изменение и удаление вебхуков
- создание, изменение и удаление приглашений
- закрепление и открепление сообщений
- добавление ботов на сервер
- массовая чистка неактивных участников
- создание, изменение и удаление эмодзи
- создание, изменение и удаление стикеров
- создание, изменение и удаление звуков саунд-панели
- запуск и остановка стримов
- включение и выключение камеры
- создание, изменение и удаление Stage
- создание, изменение и отмена запланированных событий
- создание, изменение и удаление правил AutoMod
- срабатывания AutoMod: блокировка, флаг, тайм-аут, карантин взаимодействий
- общие изменения сервера

### Что видно в логах

EVA старается показывать только полезное:

- кто выполнил действие
- кого затронуло действие
- где это произошло
- что именно изменилось
- причину из Audit Log, если Discord её отдал
- реальную длительность стрима, камеры или голосовой сессии там, где это уместно

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
ENABLE_PRESENCES_INTENT=false
ENABLE_MESSAGE_CONTENT_INTENT=false
NICK_PREFIX_RULES=1389394678561902652=🌸;1354908419567521986=🥩;1354908419332509762=💎;1388621626710429756=⭐️;1354908419332509764=👑;1354908419332509761=⚙️;1354908419332509759=🍉;1354908419332509757=🌸;1354908418846232625=🌹;1354908419332509758=🎦;1354908418846232624=🍺
NICK_PREFIX_USER_RULES=380036631584833558=💅
NICK_PREFIX_LEGACY_PREFIXES=🎲;⭕️;🎖
NICK_PREFIX_EXCLUDED_USER_IDS=495309668986388520
NICK_PREFIX_RESYNC_MINUTES=180
IGNORED_CHANNEL_IDS=1409209895382814821;1409209895382814822
PROTECTED_BANS_ENABLED=false
PROTECTED_BANS_AUTO_CAPTURE=true
PROTECTED_BANS_ENFORCE_MINUTES=5
PROTECTED_VOICE_GUARD_ENABLED=true
PROTECTED_VOICE_GUARD_USER_IDS=220189945761890304;123456789012345678
CHAT_BANTER_ENABLED=true
CHAT_BANTER_REPLY_CHANCE=0.35
CHAT_BANTER_CHANNEL_COOLDOWN_SECONDS=120
CHAT_BANTER_USER_COOLDOWN_SECONDS=300
PUBG_LOOKUP_ENABLED=false
PUBG_LOOKUP_CHANNEL_IDS=1515911648739852329
PUBG_LOOKUP_ALLOWED_ROLE_IDS=1389394678561902652;1354908419567521986
PUBG_PLATFORM=steam
PUBG_LOOKUP_INCLUDE_RANKED=true
PUBG_LOOKUP_INCLUDE_LIFETIME_STATS=false
PUBG_LOOKUP_CACHE_TTL_SECONDS=900
PUBG_LOOKUP_USER_COOLDOWN_SECONDS=20
STEAM_DIGEST_ENABLED=true
STEAM_DIGEST_CHANNEL_IDS=1354908421811601520
STEAM_DIGEST_HOUR=20
STEAM_DIGEST_MINUTE=0
STEAM_DIGEST_TIMEZONE=Europe/Simferopol
STEAM_DIGEST_TOP_COUNT=15
STEAM_DIGEST_INCLUDE_SUPPORT_STATS=true
SERVER_BANNER_ENABLED=false
SERVER_BANNER_UPDATE_MINUTES=2
SERVER_BANNER_TITLE=ROSE BLADE
SERVER_BANNER_BACKGROUND_URL=
SERVER_BANNER_BACKGROUND_PATH=roseblade_bot/assets/background.png
SERVER_BANNER_FONT_PATH=
AIR_ALERT_ENABLED=true
AIR_ALERT_CHANNEL_IDS=1518950671163068567
AIR_ALERT_PROVIDER=alerts_in_ua
AIR_ALERT_API_TOKEN=your_alerts_in_ua_token
AIR_ALERT_UBILLING_SOURCE=default
AIR_ALERT_POLL_SECONDS=30
AIR_ALERT_TITLE=Карта повітряних тривог України
AIR_ALERT_USE_WAR_MONITOR_INTEL=true
AIR_ALERT_INTEL_MAX_AGE_SECONDS=600
AIR_ALERT_BULLETIN_COOLDOWN_SECONDS=240
AIR_ALERT_HOT_REGIONS_LIMIT=5
MUSIC_ENABLED=false
MUSIC_LAVALINK_URI=http://127.0.0.1:2333
MUSIC_LAVALINK_PASSWORD=youshallnotpass
MUSIC_NODE_IDENTIFIER=eva-node
MUSIC_DEFAULT_VOLUME=70
MUSIC_INACTIVE_TIMEOUT_SECONDS=180
MUSIC_SEARCH_SOURCE=ytmsearch
MUSIC_FALLBACK_SEARCH_SOURCE=ytsearch
MUSIC_ALLOWED_ROLE_IDS=
MUSIC_SPOTIFY_CLIENT_ID=
MUSIC_SPOTIFY_CLIENT_SECRET=
MUSIC_SPOTIFY_COUNTRY_CODE=US
PUBG_API_KEY=
STEAM_API_KEY=
```

Если хочешь оставить официальный API основным, а Telegram-style монитор как дополнительную болталку, лучше развести их по разным каналам. Иначе они будут дублировать друг друга разным стилем.

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
- `Manage Nicknames`
- `Manage Server`
- `Move Members`
- `Moderate Members`
- `Manage Messages`

## Privileged Intents

Для полного покрытия логов в Discord Developer Portal желательно включить:

- `Server Members Intent`
- `Presence Intent`
- `Message Content Intent`

После этого нужно отразить это в `.env`:

```env
ENABLE_MEMBERS_INTENT=true
ENABLE_PRESENCES_INTENT=true
ENABLE_MESSAGE_CONTENT_INTENT=true
```

Без этих intents EVA всё равно работает, но часть событий будет ограничена самим Discord.

Для самых полезных логов удаления сообщений и pin/unpin желательно отдельно включать именно `Message Content Intent`, иначе Discord не всегда отдаёт текст сообщения боту.
Для автопрефиксов в никах по ролям желательно включить именно `Server Members Intent`, иначе Discord не сможет надёжно отслеживать каждую смену ника и ролей.
Для игривых ответов EVA на мат в чате `Message Content Intent` обязателен, иначе бот просто не увидит текст сообщений.

Для live-баннера с цифрой онлайна нужен именно `Presence Intent`, иначе строка онлайна будет показываться как `н/д`.

## Steam-дайджест

Если хочется, чтобы EVA вечером приносила небольшую сводку по Steam в отдельный канал, включи блок:

```env
STEAM_DIGEST_ENABLED=true
STEAM_DIGEST_CHANNEL_IDS=1354908421811601520
STEAM_DIGEST_HOUR=20
STEAM_DIGEST_MINUTE=0
STEAM_DIGEST_TIMEZONE=Europe/Simferopol
STEAM_DIGEST_TOP_COUNT=15
STEAM_DIGEST_INCLUDE_SUPPORT_STATS=true
```

Пояснение:

- `STEAM_DIGEST_CHANNEL_IDS` — один или несколько каналов через `;` или `,`
- `STEAM_DIGEST_HOUR` и `STEAM_DIGEST_MINUTE` — время публикации
- `STEAM_DIGEST_TIMEZONE` — таймзона расписания
- `STEAM_DIGEST_TOP_COUNT` — сколько игр показывать в списке
- `STEAM_DIGEST_INCLUDE_SUPPORT_STATS` — добавлять ли блок со Steam Support

Даже если бот перезапустится позже `20:00`, EVA догонит пропущенный пост в этот же день и не задублирует его повторно после рестарта.
Для ручной проверки без ожидания расписания используй `/steam_digest_now`.

## Live-баннер сервера

Если хочется, чтобы EVA каждые 2 минуты обновляла шапку Discord-сервера и рисовала на ней живую статистику, включи блок:

```env
SERVER_BANNER_ENABLED=true
SERVER_BANNER_UPDATE_MINUTES=2
SERVER_BANNER_TITLE=ROSE BLADE
SERVER_BANNER_BACKGROUND_URL=
SERVER_BANNER_BACKGROUND_PATH=roseblade_bot/assets/background.png
SERVER_BANNER_FONT_PATH=
SERVER_BANNER_EXCLUDED_CHANNEL_IDS=1409209895382814821;1484606960044347482
```

Пояснение:

- `SERVER_BANNER_UPDATE_MINUTES` — как часто EVA проверяет изменения и перерисовывает баннер
- `SERVER_BANNER_TITLE` — крупный заголовок на баннере, если нужен не `guild.name`
- `SERVER_BANNER_BACKGROUND_URL` — фон по прямой ссылке, если нужен внешний источник
- `SERVER_BANNER_BACKGROUND_PATH` — локальный файл; если путь не указан, EVA попробует встроенный `roseblade_bot/assets/background.png`
- `SERVER_BANNER_FONT_PATH` — свой `.ttf`, если нужен фирменный шрифт
- `SERVER_BANNER_EXCLUDED_CHANNEL_IDS` — список voice-каналов через `;`, которые EVA не считает в баннерной статистике

Важно:

- для апдейта шапки у бота должно быть право `Manage Server`
- для точного онлайна нужен `Presence Intent`
- если кастомный фон временно недоступен, EVA соберёт fallback-баннер и не уронит весь бот
- иконки для карточек EVA берёт из `roseblade_bot/assets/microphone.png` и `roseblade_bot/assets/user.png`
- для ручной проверки используй `/server_banner_now`

## Музыка EVA

Если хочется, чтобы EVA стала ещё и музыкальным ботом, включи блок:

```env
MUSIC_ENABLED=true
MUSIC_LAVALINK_URI=http://127.0.0.1:2333
MUSIC_LAVALINK_PASSWORD=youshallnotpass
MUSIC_NODE_IDENTIFIER=eva-node
MUSIC_DEFAULT_VOLUME=70
MUSIC_INACTIVE_TIMEOUT_SECONDS=180
MUSIC_SEARCH_SOURCE=ytmsearch
MUSIC_FALLBACK_SEARCH_SOURCE=ytsearch
MUSIC_ALLOWED_ROLE_IDS=
MUSIC_SPOTIFY_CLIENT_ID=
MUSIC_SPOTIFY_CLIENT_SECRET=
MUSIC_SPOTIFY_COUNTRY_CODE=US
```

Пояснение:

- `MUSIC_LAVALINK_URI` и `MUSIC_LAVALINK_PASSWORD` — как EVA подключается к Lavalink-ноде
- `MUSIC_DEFAULT_VOLUME` — стартовая громкость плеера
- `MUSIC_INACTIVE_TIMEOUT_SECONDS` — через сколько секунд тишины EVA сама уходит из войса
- `MUSIC_SEARCH_SOURCE` — основной поиск; для нас по умолчанию это `ytmsearch`
- `MUSIC_FALLBACK_SEARCH_SOURCE` — запасной поиск; по умолчанию `ytsearch`
- `MUSIC_ALLOWED_ROLE_IDS` — если указать роли, только они и админы смогут рулить музыкой
- `MUSIC_SPOTIFY_CLIENT_ID` и `MUSIC_SPOTIFY_CLIENT_SECRET` — включают поддержку Spotify-ссылок через mirror

Архитектура:

- сам бот использует `wavelink`
- сама музыка едет через отдельный `Lavalink`-сервер
- под `YouTube Music` включается `youtube-plugin`
- под `Spotify` включается `LavaSrc`

В репозитории для этого уже лежат шаблоны:

- `deploy/lavalink/application.yml.example`
- `deploy/lavalink/eva-lavalink.service.example`

Без поднятого Lavalink команда `/music_status` покажет, что музыкальная нода ещё не готова.

## Игривые ответы EVA в чате

EVA умеет иногда отвечать на мат в обычных чатах без удаления сообщения и без наказаний.
Она просто кокетливо троллит, просит сбавить градус и поддерживает атмосферу живой беседы.

Особенности:

- работает по русскому, украинскому и английскому пулу триггеров
- не отвечает на каждое сообщение подряд
- использует шанс ответа и cooldown по каналу и пользователю
- не лезет в аудит-каналы
- уважает каналы из `IGNORED_CHANNEL_IDS` и ignore-настроек аудита
- генерирует тысячи вариаций ответа из большого набора фраз

Настройки:

```env
IGNORED_CHANNEL_IDS=1409209895382814821;1409209895382814822
CHAT_BANTER_ENABLED=true
CHAT_BANTER_REPLY_CHANCE=0.35
CHAT_BANTER_CHANNEL_COOLDOWN_SECONDS=120
CHAT_BANTER_USER_COOLDOWN_SECONDS=300
```

## Исключённые каналы

Если есть каналы, которые EVA должна полностью обходить стороной, их можно прописать прямо в `.env`:

```env
IGNORED_CHANNEL_IDS=1409209895382814821;1409209895382814822
```

Что это даёт:

- события из этих каналов не попадут в аудит-логи
- EVA не будет отвечать там на мат и не будет поддерживать banter
- можно перечислять несколько каналов через `;`, `,` или пробел

Кроме `.env`, исключения по-прежнему можно накидывать и через slash-команды `/audit_ignore_channel` и `/audit_unignore_channel`.

## PUBG Проверка По Нику

EVA умеет в отдельном чате отвечать на обращения вроде:

- `Ева посмотри бан ник SteveDogs`
- `Ева глянь пожалуйста аккаунт S_T_E_V_E-`
- `Ева проверь pubg игрок G_O_S_P_O_Z_H_A`

Как это устроено в текущей версии:

- EVA реагирует только в каналах из `PUBG_LOOKUP_CHANNEL_IDS`
- если `PUBG_LOOKUP_ALLOWED_ROLE_IDS` заполнен, пользоваться проверкой смогут только владелец сервера и участники с этими ролями
- сообщение должно начинаться с обращения к Еве и содержать просьбу посмотреть ник PUBG
- основной запрос идёт через официальный PUBG API по `playerName`
- по нику EVA может показать статус аккаунта, тип бана, shard, clanId и число недавних матчей
- при включённом `PUBG_LOOKUP_INCLUDE_RANKED` EVA дополнительно тянет текущий ranked tier, RP и краткую ranked-сводку
- при включённом `PUBG_LOOKUP_INCLUDE_LIFETIME_STATS` EVA дополнительно тянет lifetime-статы и показывает лучший режим

Почему не делаем ставку на Steam API в этой же команде:

- официальный FAQ PUBG прямо говорит, что PUBG API не умеет получать SteamID из IGN или наоборот
- поэтому для обычной проверки по нику Steam-ключ не помогает
- `STEAM_API_KEY` оставлен в конфиге на будущее, если позже захочется отдельный режим проверки по `steamid` или `steamcommunity.com/id/...`

Настройка:

```env
PUBG_LOOKUP_ENABLED=true
PUBG_LOOKUP_CHANNEL_IDS=1515911648739852329
PUBG_LOOKUP_ALLOWED_ROLE_IDS=1389394678561902652;1354908419567521986
PUBG_PLATFORM=steam
PUBG_LOOKUP_INCLUDE_RANKED=true
PUBG_LOOKUP_INCLUDE_LIFETIME_STATS=false
PUBG_LOOKUP_CACHE_TTL_SECONDS=900
PUBG_LOOKUP_USER_COOLDOWN_SECONDS=20
PUBG_API_KEY=your_pubg_api_key
STEAM_API_KEY=your_steam_api_key
```

Что важно по лимитам:

- PUBG Developer API по умолчанию даёт `10` запросов в минуту
- простой поиск по нику стоит `1` rate-limited запрос
- поиск по нику плюс ranked-стата обычно стоит `2` запроса, потому что EVA добирает текущий сезон и ranked summary
- поиск по нику плюс lifetime-статы стоит уже `2` rate-limited запроса
- если включены и ranked, и lifetime, lookup может стоить уже `3` запроса
- EVA поэтому использует кэш и user cooldown, чтобы чат не сжигал лимит впустую

По доступу:

- если `PUBG_LOOKUP_ALLOWED_ROLE_IDS` пустой, проверкой могут пользоваться все, у кого есть доступ к каналу
- если список заполнен, EVA будет отвечать только владельцу сервера и участникам с одной из указанных ролей

Что EVA реально может достать из PUBG API:

- факт существования аккаунта на нужном shard
- `banType` из player object
- внутренний PUBG account ID
- `clanId`, если он есть
- количество недавних матчей, которые API помнит за последние `14` дней
- lifetime / season / ranked-статы, если пойдём в дополнительные запросы
- mastery, leaderboards, match data и telemetry для более глубоких сценариев

## Защита Владельца И Избранных

EVA умеет отдельно охранять владельца сервера и выбранные ID от модераторского `disconnect` из голосового канала.
Если кто-то насильно выдёргивает такого участника из войса, EVA:

- отправляет обидчику личное сообщение с фирменной колкой фразой
- если обидчик сам сидит в войсе и бот может его тронуть по иерархии, выдёргивает его из голосового канала в ответ

Настройка в `.env`:

```env
PROTECTED_VOICE_GUARD_ENABLED=true
PROTECTED_VOICE_GUARD_USER_IDS=220189945761890304;123456789012345678
```

Как это работает:

- владелец сервера попадает под защиту автоматически
- в `PROTECTED_VOICE_GUARD_USER_IDS` можно добавить ещё несколько ID через `;`, `,` или пробел
- реакция срабатывает именно на модераторский `disconnect` из войса, а не на обычный выход участника
- если у обидчика закрыты личные сообщения, EVA хотя бы попробует выдернуть его из войса

Для этой функции боту нужны:

- `View Audit Log`
- `Move Members`
- роль бота выше роли нарушителя, иначе Discord не даст его отключить

## Префиксы ников по ролям

EVA умеет автоматически добавлять префиксы к никам по ролям и возвращать их обратно, если пользователь пытается убрать префикс вручную.

Формат настройки в `.env`:

```env
NICK_PREFIX_RULES=1389394678561902652=🌸;1354908419567521986=🥩;1354908419332509762=💎;1388621626710429756=⭐️;1354908419332509764=👑;1354908419332509761=⚙️;1354908419332509759=🍉;1354908419332509757=🌸;1354908418846232625=🌹;1354908419332509758=🎦;1354908418846232624=🍺
NICK_PREFIX_USER_RULES=380036631584833558=💅
NICK_PREFIX_LEGACY_PREFIXES=🎲;⭕️;🎖
```

Можно писать и через запятую:

```env
NICK_PREFIX_RULES=1389394678561902652=🌸,1354908419567521986=🥩
NICK_PREFIX_USER_RULES=380036631584833558=💅
```

Логика работы:

- если у участника есть указанная роль, EVA ставит нужный префикс перед ником
- если для конкретного `user_id` задан `NICK_PREFIX_USER_RULES`, персональный префикс имеет приоритет над ролевым
- если префикс когда-то поменяли, старые значения можно перечислить в `NICK_PREFIX_LEGACY_PREFIXES`, и EVA будет их счищать при пересинхронизации
- если `NICK_PREFIX_EXCLUDED_USER_IDS` содержит ID участника, EVA вообще не трогает его ник
- если участник меняет ник вручную, EVA снова добавляет префикс
- если у участника несколько ролей с префиксами, EVA берёт только префикс самой высокой роли
- если роль сняли, EVA убирает управляемый префикс
- фоновая проверка дрейфа никнеймов идёт по `NICK_PREFIX_RESYNC_MINUTES`, а вручную её можно дёрнуть командой `/nick_resync`

## Защищённые пермабаны

Если нужен режим, где разбанить определённых пользователей может только владелец сервера, включи:

```env
PROTECTED_BANS_ENABLED=true
PROTECTED_BANS_AUTO_CAPTURE=true
PROTECTED_BANS_ENFORCE_MINUTES=5
```

Логика:

- новые баны автоматически попадают в owner-only список, если включён `PROTECTED_BANS_AUTO_CAPTURE`
- чужой разбан такого пользователя EVA откатывает обратно
- штатный путь для владельца: `/protected_bans_sync`, `/protected_bans_list`, `/protected_unban`
- при старте EVA сначала подтягивает текущий бан-лист Discord в защитный список, а потом сразу сверяет его и возвращает разбаненных обратно
- дальше периодическая сверка по `PROTECTED_BANS_ENFORCE_MINUTES` продолжает держать бан-лист в тонусе

Ограничения Discord:

- бот не может менять ник владельцу сервера
- бот не может менять ник участникам, чья роль выше или равна роли бота
- для работы нужны права `Manage Nicknames`

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
.editorconfig
.env.example
.gitattributes
.gitignore
LICENSE
NOTICE.md
main.py
deploy/
  lavalink/
    application.yml.example
    eva-lavalink.service.example
roseblade_bot/
  __init__.py
  assets/
    background.png
    microphone.png
    user.png
  audit/
    constants.py
    dispatcher.py
    history.py
    models.py
    renderer.py
  audit_cog_commands.py
  audit_cog_events.py
  audit_cog_runtime.py
  audit_definitions.py
  audit_logger.py
  audit_snapshots.py
  bot.py
  chat_banter.py
  cogs/
    commands.py
    core.py
    events.py
    music.py
    shared.py
  config.py
  formatters.py
  locales/
    chat_banter.toml
    ru.toml
  message_handlers.py
  music/
    lavalink_config.py
    phrases.py
    service.py
  phrases.py
  pubg_lookup.py
  server_banner.py
  services/
    http.py
  special_dm.py
  steam_digest.py
  storage.py
  voice_guard.py
  voice_handlers.py
tests/
  test_chat_banter.py
  test_config.py
  test_music_lavalink_config.py
  test_music_service.py
  test_special_dm.py
requirements.txt
```

## Брендинг

**EVA Assistant** — фирменный moderation/audit проект от **Steve Dogs Studio**.

- Сайт: [steve.dog](https://steve.dog)
- Telegram: [t.me/stevedog](https://t.me/stevedog)
- GitHub: [SteveDogs/EvaAssistantDiscord](https://github.com/SteveDogs/EvaAssistantDiscord)

## Дорожная карта

- стили поведения и настроения Евы
- переключаемые режимы тона логов
- улучшение выгрузки истории
- веб-панель или административный интерфейс
- ещё более глубокая интеграция anti-spam и AutoMod

## Копирайт

Copyright (c) 2026 Steve Dogs Studio.

В этом репозитории размещены исходный код, брендированные материалы и публичная витрина проекта EVA Assistant.

## Лицензия

Репозиторий распространяется по лицензии **Apache License 2.0**.

Это значит:

- код можно использовать, форкать, дорабатывать, разворачивать и публиковать, включая коммерческое использование
- при распространении и публичном переиспользовании нужно сохранять `LICENSE` и `NOTICE.md`
- `NOTICE.md` закрепляет атрибуцию **Steve Dogs Studio** и ссылку на [steve.dog](https://steve.dog)
- изменённые файлы и неофициальные сборки должны явно обозначаться как изменённые
- название, логотипы и фирменный стиль EVA Assistant не передаются как товарные знаки автоматически

Полные условия лежат в файле [LICENSE](LICENSE) и дополняются [NOTICE.md](NOTICE.md).
