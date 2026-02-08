# Discord Server Bot

A multi-purpose Discord bot built with Python and discord.py. Combines moderation, utility commands, and API integrations in a single self-hosted bot.

## Features

### Moderation
- **Auto-moderation** — configurable word filter, spam detection (repeated messages), link filtering
- **Kick / Ban / Mute** — slash commands with reason logging and DM notification to the user
- **Mod log** — all moderation actions logged to a dedicated channel with timestamps and moderator info

### Server Management
- **Welcome messages** — customizable embed sent to a welcome channel when a member joins, with auto-role assignment
- **Ticket system** — members create support tickets via a button; each ticket gets a private channel, can be closed/archived
- **Role menu** — reaction-based role assignment: click an emoji, get a role

### Utility Commands
- **Server info** — `/serverinfo` shows member count, creation date, boost level, channels
- **User info** — `/userinfo @user` shows join date, roles, account age
- **Poll** — `/poll "Question" "Option1" "Option2"` creates a reaction poll

### API Integrations
- **Weather** — `/weather London` fetches current weather from OpenWeatherMap API
- **Currency** — `/convert 100 USD EUR` converts currency via exchangerate-api.com

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Bot Framework | discord.py 2.x |
| Database | SQLite + aiosqlite |
| Slash Commands | discord.app_commands |
| HTTP Client | aiohttp |
| Config | python-dotenv |

## Project Structure

```
discord-bot/
├── bot/
│   ├── main.py              # Entry point, bot startup, cog loading
│   ├── config.py            # Settings from .env
│   ├── cogs/
│   │   ├── moderation.py    # Kick, ban, mute, auto-mod, mod log
│   │   ├── welcome.py       # Join/leave events, auto-role
│   │   ├── tickets.py       # Ticket creation, close, archive
│   │   ├── roles.py         # Reaction role menu
│   │   ├── utility.py       # Server info, user info, poll
│   │   └── integrations.py  # Weather, currency API commands
│   └── utils/
│       ├── database.py      # SQLite models & queries
│       ├── embeds.py        # Embed builder helpers
│       └── permissions.py   # Permission check decorators
├── data/
│   └── config.json          # Per-server settings (welcome channel, mod log channel, etc.)
├── tests/
│   ├── test_moderation.py
│   ├── test_welcome.py
│   ├── test_tickets.py
│   ├── test_utility.py
│   └── test_integrations.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Commands

### Moderation (requires Manage Messages permission)

| Command | Description |
|---------|-------------|
| `/kick @user [reason]` | Kick a member with optional reason |
| `/ban @user [reason]` | Ban a member with optional reason |
| `/mute @user <duration>` | Timeout a member (e.g., `10m`, `1h`, `1d`) |
| `/purge <count>` | Delete last N messages in channel |
| `/warn @user <reason>` | Issue a warning (stored in DB) |
| `/warnings @user` | View warnings for a user |

### Utility

| Command | Description |
|---------|-------------|
| `/serverinfo` | Server statistics and info |
| `/userinfo @user` | User account and role info |
| `/poll "Q" "A" "B"` | Create a reaction poll (2-9 options) |
| `/ticket` | Open a support ticket |

### Integrations

| Command | Description |
|---------|-------------|
| `/weather <city>` | Current weather for a city |
| `/convert <amount> <from> <to>` | Currency conversion |

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/fedorvorobyov/discord-bot.git
cd discord-bot
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your values:
- `DISCORD_TOKEN` — Get from [Discord Developer Portal](https://discord.com/developers/applications)
- `OPENWEATHER_API_KEY` — Free key from [OpenWeatherMap](https://openweathermap.org/api)

### 5. Run the bot

```bash
python -m bot.main
```

### 6. Invite to your server

Use the OAuth2 URL from the Developer Portal with these permissions:
- Manage Roles, Manage Channels, Kick Members, Ban Members
- Send Messages, Manage Messages, Embed Links, Add Reactions
- Use Slash Commands

## Configuration

Per-server settings are stored in `data/config.json`:

```json
{
  "welcome_channel": "welcome",
  "mod_log_channel": "mod-log",
  "ticket_category": "Support Tickets",
  "auto_role": "Member",
  "word_filter": ["badword1", "badword2"],
  "spam_threshold": 5,
  "spam_interval": 10
}
```

## License

MIT
