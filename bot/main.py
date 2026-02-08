import asyncio
import logging

import discord
from discord.ext import commands

from bot import config
from bot.utils.database import init_db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cog extensions to load on startup
# ---------------------------------------------------------------------------
INITIAL_EXTENSIONS: list[str] = [
    "bot.cogs.moderation",
    "bot.cogs.welcome",
    "bot.cogs.tickets",
    "bot.cogs.roles",
    "bot.cogs.utility",
    "bot.cogs.integrations",
]


# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
async def main() -> None:
    """Entry point: create the bot, load extensions, and start."""

    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix="!", intents=intents)

    # -- Events ------------------------------------------------------------

    @bot.event
    async def on_ready() -> None:
        """Sync application (slash) commands once the bot is connected."""
        assert bot.user is not None
        synced = await bot.tree.sync()
        log.info(
            "Logged in as %s (ID: %s) | Synced %d slash command(s)",
            bot.user,
            bot.user.id,
            len(synced),
        )

    # -- Startup sequence --------------------------------------------------

    async with bot:
        # Initialise the database before anything else
        await init_db()
        log.info("Database initialised at %s", config.DATABASE_PATH)

        # Load all cog extensions
        for extension in INITIAL_EXTENSIONS:
            try:
                await bot.load_extension(extension)
                log.info("Loaded extension: %s", extension)
            except Exception:
                log.exception("Failed to load extension: %s", extension)

        # Run the bot (blocks until the bot is closed)
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
