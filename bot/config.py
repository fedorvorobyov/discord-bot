import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Discord bot token (required)
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")

# OpenWeatherMap API key (optional, used by weather commands)
OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")

# Project root is one level above the bot/ package
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# SQLite database path
DATABASE_PATH: str = str(PROJECT_ROOT / "data" / "bot.db")

# JSON configuration path
CONFIG_PATH: str = str(PROJECT_ROOT / "data" / "config.json")
