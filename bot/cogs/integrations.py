"""Integrations cog -- external API commands (weather, currency conversion).

Provides slash commands that query third-party services and return
nicely formatted embed responses.
"""

from __future__ import annotations

import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot import config
from bot.utils.embeds import error_embed, info_embed, success_embed

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
_EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/{base}"


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class Integrations(commands.Cog):
    """Slash commands that integrate with external APIs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()

    async def cog_unload(self) -> None:
        if self.session is not None:
            await self.session.close()

    # ==================================================================
    # Slash commands
    # ==================================================================

    # --- /weather -----------------------------------------------------

    @app_commands.command(
        name="weather",
        description="Get the current weather for a city",
    )
    @app_commands.describe(city="Name of the city to look up")
    async def weather(
        self,
        interaction: discord.Interaction,
        city: str,
    ) -> None:
        assert self.session is not None

        if not config.OPENWEATHER_API_KEY:
            await interaction.response.send_message(
                embed=error_embed(
                    "API Configuration Error",
                    "The OpenWeatherMap API key has not been configured.",
                ),
                ephemeral=True,
            )
            return

        params = {
            "q": city,
            "appid": config.OPENWEATHER_API_KEY,
            "units": "metric",
        }

        try:
            async with self.session.get(_OPENWEATHER_URL, params=params) as resp:
                if resp.status == 404:
                    await interaction.response.send_message(
                        embed=error_embed(
                            "City Not Found",
                            f"Could not find a city matching **{city}**. "
                            "Please check the spelling and try again.",
                        ),
                        ephemeral=True,
                    )
                    return

                if resp.status == 401:
                    log.error("OpenWeatherMap API key is invalid or expired")
                    await interaction.response.send_message(
                        embed=error_embed(
                            "API Configuration Error",
                            "The weather API key is invalid. "
                            "Please contact a bot administrator.",
                        ),
                        ephemeral=True,
                    )
                    return

                if resp.status != 200:
                    log.warning(
                        "OpenWeatherMap returned unexpected status %d",
                        resp.status,
                    )
                    await interaction.response.send_message(
                        embed=error_embed(
                            "Weather Error",
                            "Could not fetch weather data. Please try again later.",
                        ),
                        ephemeral=True,
                    )
                    return

                data = await resp.json()

        except (aiohttp.ClientError, TimeoutError):
            log.exception("Network error while fetching weather data")
            await interaction.response.send_message(
                embed=error_embed(
                    "Network Error",
                    "Could not fetch weather data. Please try again later.",
                ),
                ephemeral=True,
            )
            return

        # Build the embed from the API response
        city_name: str = data["name"]
        weather_info = data["weather"][0]
        main_info = data["main"]
        wind_info = data["wind"]

        icon_code: str = weather_info["icon"]
        icon_url = f"https://openweathermap.org/img/wn/{icon_code}@2x.png"

        embed = info_embed(title=f"Weather in {city_name}")
        embed.set_thumbnail(url=icon_url)
        embed.add_field(
            name="Temperature",
            value=f"{main_info['temp']}\u00b0C (feels like: {main_info['feels_like']}\u00b0C)",
            inline=True,
        )
        embed.add_field(
            name="Description",
            value=weather_info["description"].capitalize(),
            inline=True,
        )
        embed.add_field(
            name="Humidity",
            value=f"{main_info['humidity']}%",
            inline=True,
        )
        embed.add_field(
            name="Wind",
            value=f"{wind_info['speed']} m/s",
            inline=True,
        )
        embed.add_field(
            name="Pressure",
            value=f"{main_info['pressure']} hPa",
            inline=True,
        )
        embed.set_footer(text="Powered by OpenWeatherMap")

        await interaction.response.send_message(embed=embed)

    # --- /convert -----------------------------------------------------

    @app_commands.command(
        name="convert",
        description="Convert an amount between two currencies",
    )
    @app_commands.describe(
        amount="The amount to convert (must be greater than 0)",
        from_currency="Source currency code (e.g. USD, EUR, GBP)",
        to_currency="Target currency code (e.g. USD, EUR, GBP)",
    )
    async def convert(
        self,
        interaction: discord.Interaction,
        amount: float,
        from_currency: str,
        to_currency: str,
    ) -> None:
        assert self.session is not None

        # Validate amount
        if amount <= 0:
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Amount",
                    "The amount must be greater than **0**.",
                ),
                ephemeral=True,
            )
            return

        # Normalise and validate currency codes
        from_currency = from_currency.upper().strip()
        to_currency = to_currency.upper().strip()

        if len(from_currency) != 3 or not from_currency.isalpha():
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Currency Code",
                    f"**{from_currency}** is not a valid 3-letter currency code.",
                ),
                ephemeral=True,
            )
            return

        if len(to_currency) != 3 or not to_currency.isalpha():
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Currency Code",
                    f"**{to_currency}** is not a valid 3-letter currency code.",
                ),
                ephemeral=True,
            )
            return

        url = _EXCHANGE_RATE_URL.format(base=from_currency)

        try:
            async with self.session.get(url) as resp:
                data = await resp.json()

        except (aiohttp.ClientError, TimeoutError):
            log.exception("Network error while fetching exchange rates")
            await interaction.response.send_message(
                embed=error_embed(
                    "Network Error",
                    "Could not fetch exchange rate data. Please try again later.",
                ),
                ephemeral=True,
            )
            return

        # The API returns "result": "success" on success
        if data.get("result") != "success":
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Currency",
                    f"**{from_currency}** is not a supported currency code.",
                ),
                ephemeral=True,
            )
            return

        rates: dict[str, float] = data.get("rates", {})

        if to_currency not in rates:
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Currency",
                    f"**{to_currency}** is not a supported currency code.",
                ),
                ephemeral=True,
            )
            return

        rate: float = rates[to_currency]
        result = round(amount * rate, 2)

        last_updated: str = data.get("time_last_update_utc", "Unknown")

        embed = success_embed(
            title="Currency Conversion",
            description=f"**{amount:,.2f} {from_currency}** = **{result:,.2f} {to_currency}**",
        )
        embed.add_field(
            name="Rate",
            value=f"1 {from_currency} = {rate} {to_currency}",
            inline=True,
        )
        embed.add_field(
            name="Last Updated",
            value=last_updated,
            inline=True,
        )
        embed.set_footer(text="Powered by exchangerate-api.com")

        await interaction.response.send_message(embed=embed)

    # ==================================================================
    # Error handler
    # ==================================================================

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle errors raised by slash commands in this cog."""
        log.exception("Unhandled error in integrations cog", exc_info=error)

        embed = error_embed(
            "Unexpected Error",
            "Something went wrong. Please try again later.",
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Extension setup
# ---------------------------------------------------------------------------


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Integrations(bot))
