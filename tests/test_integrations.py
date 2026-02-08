"""Tests for the integrations cog.

Covers /weather and /convert commands with mocked API responses,
including error paths (404, 401, invalid currency, amount validation).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import discord
import pytest

from bot import config
from bot.cogs.integrations import Integrations


# ===================================================================
# Helper: create a mock aiohttp response
# ===================================================================


def _make_response(
    status: int = 200,
    json_data: dict | None = None,
) -> MagicMock:
    """Create a mock aiohttp response as an async context manager."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})

    # Make it work as an async context manager
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ===================================================================
# /weather tests
# ===================================================================


class TestWeatherCommand:
    """Tests for the /weather slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.cog = Integrations(self.bot)
        self.cog.session = MagicMock(spec=aiohttp.ClientSession)

        # Patch the API key to a non-empty value
        self._api_patch = patch.object(
            config, "OPENWEATHER_API_KEY", "test-api-key-123"
        )
        self._api_patch.start()

    def teardown_method(self) -> None:
        self._api_patch.stop()

    async def test_weather_success_shows_embed_fields(self) -> None:
        """Verify a successful weather response produces an embed with fields."""
        json_data = {
            "name": "London",
            "weather": [
                {
                    "description": "clear sky",
                    "icon": "01d",
                }
            ],
            "main": {
                "temp": 15.5,
                "feels_like": 14.2,
                "humidity": 72,
                "pressure": 1013,
            },
            "wind": {
                "speed": 3.1,
            },
        }
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.weather.callback(
            self.cog, self.interaction, city="London"
        )

        self.interaction.response.send_message.assert_awaited_once()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "London" in embed.title

        field_names = [f.name for f in embed.fields]
        assert "Temperature" in field_names
        assert "Description" in field_names
        assert "Humidity" in field_names
        assert "Wind" in field_names
        assert "Pressure" in field_names

    async def test_weather_temperature_in_field(self) -> None:
        """Verify the temperature value appears in the embed."""
        json_data = {
            "name": "Paris",
            "weather": [{"description": "cloudy", "icon": "04d"}],
            "main": {
                "temp": 22.0,
                "feels_like": 21.0,
                "humidity": 60,
                "pressure": 1015,
            },
            "wind": {"speed": 5.0},
        }
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.weather.callback(
            self.cog, self.interaction, city="Paris"
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        temp_field = next(f for f in embed.fields if f.name == "Temperature")
        assert "22.0" in temp_field.value

    async def test_weather_city_not_found_404(self) -> None:
        """Verify a 404 response produces a 'City Not Found' error embed."""
        self.cog.session.get = MagicMock(
            return_value=_make_response(404)
        )

        await self.cog.weather.callback(
            self.cog, self.interaction, city="Nonexistent"
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Not Found" in embed.title
        assert call_kwargs.kwargs.get("ephemeral") is True

    async def test_weather_invalid_api_key_401(self) -> None:
        """Verify a 401 response produces an API error embed."""
        self.cog.session.get = MagicMock(
            return_value=_make_response(401)
        )

        await self.cog.weather.callback(
            self.cog, self.interaction, city="London"
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "API" in embed.title or "Configuration" in embed.title
        assert call_kwargs.kwargs.get("ephemeral") is True

    async def test_weather_no_api_key_configured(self) -> None:
        """Verify an error when the API key is empty."""
        with patch.object(config, "OPENWEATHER_API_KEY", ""):
            await self.cog.weather.callback(
                self.cog, self.interaction, city="London"
            )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Configuration" in embed.title

    async def test_weather_unexpected_status(self) -> None:
        """Verify a non-200/401/404 status returns a generic error."""
        self.cog.session.get = MagicMock(
            return_value=_make_response(500)
        )

        await self.cog.weather.callback(
            self.cog, self.interaction, city="London"
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Error" in embed.title

    async def test_weather_footer_shows_attribution(self) -> None:
        """Verify the embed footer credits OpenWeatherMap."""
        json_data = {
            "name": "Berlin",
            "weather": [{"description": "rain", "icon": "10d"}],
            "main": {
                "temp": 10.0,
                "feels_like": 8.0,
                "humidity": 85,
                "pressure": 1008,
            },
            "wind": {"speed": 7.0},
        }
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.weather.callback(
            self.cog, self.interaction, city="Berlin"
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert "OpenWeatherMap" in embed.footer.text


# ===================================================================
# /convert tests
# ===================================================================


class TestConvertCommand:
    """Tests for the /convert slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.cog = Integrations(self.bot)
        self.cog.session = MagicMock(spec=aiohttp.ClientSession)

    async def test_convert_success(self) -> None:
        """Verify a successful conversion returns the correct result."""
        json_data = {
            "result": "success",
            "rates": {
                "USD": 1.0,
                "EUR": 0.85,
                "GBP": 0.73,
            },
            "time_last_update_utc": "Mon, 01 Jan 2024 00:00:01 +0000",
        }
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=100.0,
            from_currency="USD",
            to_currency="EUR",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Currency Conversion" in embed.title
        # 100 * 0.85 = 85.0
        assert "85.00" in embed.description

    async def test_convert_rate_field(self) -> None:
        """Verify the rate field is included in the response embed."""
        json_data = {
            "result": "success",
            "rates": {"EUR": 0.85},
            "time_last_update_utc": "Mon, 01 Jan 2024 00:00:01 +0000",
        }
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=50.0,
            from_currency="USD",
            to_currency="EUR",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Rate" in field_names

    async def test_convert_invalid_from_currency(self) -> None:
        """Verify an error when the source currency is not supported."""
        json_data = {"result": "error"}
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=100.0,
            from_currency="XYZ",
            to_currency="USD",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Invalid" in embed.title or "Currency" in embed.title

    async def test_convert_invalid_to_currency(self) -> None:
        """Verify an error when the target currency is not found in rates."""
        json_data = {
            "result": "success",
            "rates": {"EUR": 0.85},
            "time_last_update_utc": "Mon, 01 Jan 2024",
        }
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=100.0,
            from_currency="USD",
            to_currency="ZZZ",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Invalid" in embed.title or "Currency" in embed.title

    async def test_convert_amount_zero_rejected(self) -> None:
        """Verify amount <= 0 is rejected with a validation error."""
        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=0,
            from_currency="USD",
            to_currency="EUR",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Invalid" in embed.title or "Amount" in embed.title
        assert call_kwargs.kwargs.get("ephemeral") is True

    async def test_convert_negative_amount_rejected(self) -> None:
        """Verify negative amounts are rejected."""
        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=-50.0,
            from_currency="USD",
            to_currency="EUR",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Invalid" in embed.title or "Amount" in embed.title

    async def test_convert_bad_currency_code_format(self) -> None:
        """Verify a non-alpha or wrong-length currency code is rejected."""
        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=10.0,
            from_currency="US",
            to_currency="EUR",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Invalid" in embed.title

    async def test_convert_numeric_currency_code_rejected(self) -> None:
        """Verify numeric-only currency codes are rejected."""
        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=10.0,
            from_currency="123",
            to_currency="EUR",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Invalid" in embed.title

    async def test_convert_currencies_are_uppercased(self) -> None:
        """Verify lowercase currency inputs are normalized to uppercase."""
        json_data = {
            "result": "success",
            "rates": {"EUR": 0.85},
            "time_last_update_utc": "Mon, 01 Jan 2024",
        }
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=10.0,
            from_currency="usd",
            to_currency="eur",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "USD" in embed.description
        assert "EUR" in embed.description

    async def test_convert_last_updated_field(self) -> None:
        """Verify the 'Last Updated' field is present."""
        json_data = {
            "result": "success",
            "rates": {"GBP": 0.73},
            "time_last_update_utc": "Tue, 02 Jan 2024 00:00:01 +0000",
        }
        self.cog.session.get = MagicMock(
            return_value=_make_response(200, json_data)
        )

        await self.cog.convert.callback(
            self.cog,
            self.interaction,
            amount=1.0,
            from_currency="USD",
            to_currency="GBP",
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Last Updated" in field_names
