"""Tests for the moderation cog.

Covers kick, ban, mute, purge, warn, and warnings commands, as well as
the duration parser used by /mute.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot import config
from bot.cogs.moderation import Moderation, _parse_duration
from bot.utils.database import add_warning, get_warning_count, get_warnings


# ===================================================================
# Duration parser unit tests
# ===================================================================


class TestParseDuration:
    """Unit tests for ``_parse_duration``."""

    def test_parse_seconds(self) -> None:
        result = _parse_duration("30s")
        assert result == timedelta(seconds=30)

    def test_parse_minutes(self) -> None:
        result = _parse_duration("10m")
        assert result is not None
        assert result.total_seconds() == 600

    def test_parse_hours(self) -> None:
        result = _parse_duration("1h")
        assert result is not None
        assert result.total_seconds() == 3600

    def test_parse_days(self) -> None:
        result = _parse_duration("1d")
        assert result is not None
        assert result.total_seconds() == 86400

    def test_parse_with_whitespace(self) -> None:
        result = _parse_duration("  5m  ")
        assert result is not None
        assert result.total_seconds() == 300

    def test_parse_uppercase(self) -> None:
        result = _parse_duration("2H")
        assert result is not None
        assert result.total_seconds() == 7200

    def test_parse_invalid_no_unit(self) -> None:
        result = _parse_duration("100")
        assert result is None

    def test_parse_invalid_no_number(self) -> None:
        result = _parse_duration("m")
        assert result is None

    def test_parse_invalid_bad_unit(self) -> None:
        result = _parse_duration("10x")
        assert result is None

    def test_parse_empty_string(self) -> None:
        result = _parse_duration("")
        assert result is None

    def test_parse_invalid_words(self) -> None:
        result = _parse_duration("ten minutes")
        assert result is None

    def test_parse_zero_value(self) -> None:
        result = _parse_duration("0m")
        assert result is not None
        assert result.total_seconds() == 0


# ===================================================================
# Moderation cog command tests
# ===================================================================


class TestKickCommand:
    """Tests for the /kick slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_target: MagicMock,
        mock_config_file: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.target = mock_target

        # Patch config path so _load_config reads the temp file
        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        # Set up mod-log channel in the guild
        mod_log_channel = MagicMock(spec=discord.TextChannel)
        mod_log_channel.name = "mod-log"
        mod_log_channel.send = AsyncMock()
        self.mod_log_channel = mod_log_channel
        self.interaction.guild.text_channels = [mod_log_channel]

        self.cog = Moderation(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()

    async def test_kick_calls_member_kick(self) -> None:
        """Verify that member.kick() is called with the provided reason."""
        await self.cog.kick.callback(
            self.cog, self.interaction, self.target, reason="Test reason"
        )
        self.target.kick.assert_awaited_once_with(reason="Test reason")

    async def test_kick_sends_mod_log(self) -> None:
        """Verify that a mod log embed is sent to the mod-log channel."""
        await self.cog.kick.callback(
            self.cog, self.interaction, self.target, reason="Test reason"
        )
        self.mod_log_channel.send.assert_awaited_once()
        call_kwargs = self.mod_log_channel.send.call_args
        embed = call_kwargs.kwargs.get("embed") or call_kwargs.args[0]
        assert embed is not None

    async def test_kick_sends_success_response(self) -> None:
        """Verify the interaction gets a success response."""
        await self.cog.kick.callback(
            self.cog, self.interaction, self.target, reason="Test reason"
        )
        self.interaction.response.send_message.assert_awaited()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Kicked" in embed.title

    async def test_kick_dms_target(self) -> None:
        """Verify the target receives a DM before being kicked."""
        await self.cog.kick.callback(
            self.cog, self.interaction, self.target, reason="Test reason"
        )
        self.target.send.assert_awaited_once()

    async def test_kick_higher_role_refused(self) -> None:
        """Verify kick is refused when target has a higher role."""
        # Make the target's role higher than the bot's
        self.target.top_role.position = 100
        await self.cog.kick.callback(
            self.cog, self.interaction, self.target, reason="Test"
        )
        self.target.kick.assert_not_awaited()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Cannot" in embed.title


class TestBanCommand:
    """Tests for the /ban slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_target: MagicMock,
        mock_config_file: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.target = mock_target

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        mod_log_channel = MagicMock(spec=discord.TextChannel)
        mod_log_channel.name = "mod-log"
        mod_log_channel.send = AsyncMock()
        self.mod_log_channel = mod_log_channel
        self.interaction.guild.text_channels = [mod_log_channel]

        self.cog = Moderation(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()

    async def test_ban_calls_member_ban(self) -> None:
        """Verify that member.ban() is called with the provided reason."""
        await self.cog.ban.callback(
            self.cog, self.interaction, self.target, reason="Ban reason"
        )
        self.target.ban.assert_awaited_once_with(reason="Ban reason")

    async def test_ban_sends_success_response(self) -> None:
        """Verify the interaction gets a success response."""
        await self.cog.ban.callback(
            self.cog, self.interaction, self.target, reason="Ban reason"
        )
        self.interaction.response.send_message.assert_awaited()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Banned" in embed.title

    async def test_ban_sends_mod_log(self) -> None:
        """Verify that a mod log embed is sent."""
        await self.cog.ban.callback(
            self.cog, self.interaction, self.target, reason="Ban reason"
        )
        self.mod_log_channel.send.assert_awaited_once()

    async def test_ban_higher_role_refused(self) -> None:
        """Verify ban is refused when target outranks the bot."""
        self.target.top_role.position = 100
        await self.cog.ban.callback(
            self.cog, self.interaction, self.target, reason="Test"
        )
        self.target.ban.assert_not_awaited()


class TestMuteCommand:
    """Tests for the /mute slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_target: MagicMock,
        mock_config_file: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.target = mock_target

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        mod_log_channel = MagicMock(spec=discord.TextChannel)
        mod_log_channel.name = "mod-log"
        mod_log_channel.send = AsyncMock()
        self.interaction.guild.text_channels = [mod_log_channel]

        self.cog = Moderation(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()

    async def test_mute_calls_timeout_with_correct_timedelta(self) -> None:
        """Verify member.timeout() is called with the parsed duration."""
        await self.cog.mute.callback(
            self.cog, self.interaction, self.target, duration="10m"
        )
        self.target.timeout.assert_awaited_once()
        call_args = self.target.timeout.call_args
        delta = call_args.args[0]
        assert isinstance(delta, timedelta)
        assert delta.total_seconds() == 600

    async def test_mute_1h_duration(self) -> None:
        """Verify 1h duration is passed correctly."""
        await self.cog.mute.callback(
            self.cog, self.interaction, self.target, duration="1h"
        )
        self.target.timeout.assert_awaited_once()
        delta = self.target.timeout.call_args.args[0]
        assert delta.total_seconds() == 3600

    async def test_mute_invalid_duration_rejected(self) -> None:
        """Verify an invalid duration string is rejected with an error embed."""
        await self.cog.mute.callback(
            self.cog, self.interaction, self.target, duration="abc"
        )
        self.target.timeout.assert_not_awaited()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Invalid" in embed.title

    async def test_mute_exceeds_max_duration_rejected(self) -> None:
        """Verify durations exceeding 28 days are rejected."""
        await self.cog.mute.callback(
            self.cog, self.interaction, self.target, duration="30d"
        )
        self.target.timeout.assert_not_awaited()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Too Long" in embed.title

    async def test_mute_higher_role_refused(self) -> None:
        """Verify mute is refused when target outranks the bot."""
        self.target.top_role.position = 100
        await self.cog.mute.callback(
            self.cog, self.interaction, self.target, duration="10m"
        )
        self.target.timeout.assert_not_awaited()


class TestPurgeCommand:
    """Tests for the /purge slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_config_file: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        # Make the channel a TextChannel for isinstance check
        self.interaction.channel = MagicMock(spec=discord.TextChannel)
        self.interaction.channel.purge = AsyncMock(
            return_value=[MagicMock()] * 10
        )

        self.cog = Moderation(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()

    async def test_purge_calls_channel_purge(self) -> None:
        """Verify channel.purge() is called with the specified limit."""
        await self.cog.purge.callback(self.cog, self.interaction, count=10)
        self.interaction.channel.purge.assert_awaited_once_with(limit=10)

    async def test_purge_defers_ephemerally(self) -> None:
        """Verify the interaction is deferred as ephemeral."""
        await self.cog.purge.callback(self.cog, self.interaction, count=5)
        self.interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    async def test_purge_sends_followup(self) -> None:
        """Verify the followup message reports the number of deleted messages."""
        await self.cog.purge.callback(self.cog, self.interaction, count=10)
        self.interaction.followup.send.assert_awaited_once()
        call_kwargs = self.interaction.followup.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "10" in embed.description


class TestWarnCommand:
    """Tests for the /warn slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_target: MagicMock,
        mock_config_file: MagicMock,
        setup_database: None,
        tmp_path: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.target = mock_target
        self.tmp_path = tmp_path

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        # Patch DATABASE_PATH for the warn command's DB calls
        self._db_patch = patch.object(
            config, "DATABASE_PATH", str(tmp_path / "test_bot.db")
        )
        self._db_patch.start()

        mod_log_channel = MagicMock(spec=discord.TextChannel)
        mod_log_channel.name = "mod-log"
        mod_log_channel.send = AsyncMock()
        self.mod_log_channel = mod_log_channel
        self.interaction.guild.text_channels = [mod_log_channel]

        self.cog = Moderation(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()
        self._db_patch.stop()

    async def test_warn_saves_to_database(self) -> None:
        """Verify that warn persists the warning in the database."""
        await self.cog.warn.callback(
            self.cog, self.interaction, self.target, reason="Test warning"
        )

        count = await get_warning_count(
            self.interaction.guild.id, self.target.id
        )
        assert count == 1

    async def test_warn_returns_total_count(self) -> None:
        """Verify the response includes the total warning count."""
        # Add a pre-existing warning
        await add_warning(
            guild_id=self.interaction.guild.id,
            user_id=self.target.id,
            moderator_id=self.interaction.user.id,
            reason="Pre-existing warning",
        )

        await self.cog.warn.callback(
            self.cog, self.interaction, self.target, reason="Second warning"
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        # Total should be 2
        assert "2" in embed.description

    async def test_warn_sends_mod_log(self) -> None:
        """Verify a mod log embed is sent after warning."""
        await self.cog.warn.callback(
            self.cog, self.interaction, self.target, reason="Test warning"
        )
        self.mod_log_channel.send.assert_awaited_once()

    async def test_warn_dms_target(self) -> None:
        """Verify the target receives a DM about the warning."""
        await self.cog.warn.callback(
            self.cog, self.interaction, self.target, reason="Test warning"
        )
        self.target.send.assert_awaited_once()


class TestWarningsCommand:
    """Tests for the /warnings slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_target: MagicMock,
        mock_config_file: MagicMock,
        setup_database: None,
        tmp_path: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.target = mock_target
        self.tmp_path = tmp_path

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        self._db_patch = patch.object(
            config, "DATABASE_PATH", str(tmp_path / "test_bot.db")
        )
        self._db_patch.start()

        self.cog = Moderation(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()
        self._db_patch.stop()

    async def test_warnings_no_records(self) -> None:
        """Verify a 'no warnings' message when there are none."""
        await self.cog.warnings.callback(
            self.cog, self.interaction, self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "No Warnings" in embed.title

    async def test_warnings_with_records(self) -> None:
        """Verify warnings are listed when they exist."""
        # Insert warnings into the DB
        await add_warning(
            guild_id=self.interaction.guild.id,
            user_id=self.target.id,
            moderator_id=self.interaction.user.id,
            reason="First warning",
        )
        await add_warning(
            guild_id=self.interaction.guild.id,
            user_id=self.target.id,
            moderator_id=self.interaction.user.id,
            reason="Second warning",
        )

        # Mock get_member so mod display works
        self.interaction.guild.get_member = MagicMock(
            return_value=self.interaction.user
        )

        await self.cog.warnings.callback(
            self.cog, self.interaction, self.target
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Warnings for" in embed.title
        assert "First warning" in embed.description
        assert "Second warning" in embed.description
        assert embed.footer.text is not None
        assert "2" in embed.footer.text

    async def test_warnings_embed_fields_contain_reason_and_mod(self) -> None:
        """Verify each warning entry includes the reason and moderator."""
        await add_warning(
            guild_id=self.interaction.guild.id,
            user_id=self.target.id,
            moderator_id=self.interaction.user.id,
            reason="Specific reason text",
        )
        self.interaction.guild.get_member = MagicMock(
            return_value=self.interaction.user
        )

        await self.cog.warnings.callback(
            self.cog, self.interaction, self.target
        )

        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert "Specific reason text" in embed.description
        assert "Moderator" in embed.description
