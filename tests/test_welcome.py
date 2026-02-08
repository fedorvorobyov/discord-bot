"""Tests for the welcome cog.

Covers on_member_join (welcome embed + auto-role), on_member_remove
(leave message), and the configuration commands /setwelcome and /setautorole.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot import config
from bot.cogs.welcome import Welcome


class TestOnMemberJoin:
    """Tests for the ``on_member_join`` event listener."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_member: MagicMock,
        mock_guild: MagicMock,
        mock_config_file: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.member = mock_member
        self.guild = mock_guild
        self.member.guild = self.guild
        self.config_file = mock_config_file

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        # Set up welcome channel in the guild
        welcome_channel = MagicMock(spec=discord.TextChannel)
        welcome_channel.name = "welcome"
        welcome_channel.send = AsyncMock()
        self.welcome_channel = welcome_channel
        self.guild.text_channels = [welcome_channel]

        # Set up auto-role
        member_role = MagicMock(spec=discord.Role)
        member_role.name = "Member"
        self.member_role = member_role
        self.guild.roles = [self.guild.default_role, member_role]

        self.cog = Welcome(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()

    async def test_welcome_embed_sent_to_correct_channel(self) -> None:
        """Verify a welcome embed is sent to the configured channel."""
        await self.cog.on_member_join(self.member)
        self.welcome_channel.send.assert_awaited_once()
        call_kwargs = self.welcome_channel.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Welcome" in embed.title

    async def test_auto_role_assigned(self) -> None:
        """Verify the configured auto-role is added to the member."""
        await self.cog.on_member_join(self.member)
        self.member.add_roles.assert_awaited_once_with(
            self.member_role, reason="Auto-role on join"
        )

    async def test_no_auto_role_when_config_empty(self) -> None:
        """Verify no role is assigned when auto_role config is empty."""
        # Overwrite the config to remove auto_role
        cfg = json.loads(self.config_file.read_text())
        cfg["auto_role"] = ""
        self.config_file.write_text(json.dumps(cfg))

        await self.cog.on_member_join(self.member)
        self.member.add_roles.assert_not_awaited()

    async def test_no_welcome_when_channel_missing(self) -> None:
        """Verify no error when the welcome channel does not exist."""
        self.guild.text_channels = []  # No channels
        await self.cog.on_member_join(self.member)
        # Should not raise, auto-role should still be attempted
        self.member.add_roles.assert_awaited_once()

    async def test_welcome_embed_contains_member_mention(self) -> None:
        """Verify the welcome embed includes the new member's mention."""
        await self.cog.on_member_join(self.member)
        call_kwargs = self.welcome_channel.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert self.member.mention in embed.description


class TestOnMemberRemove:
    """Tests for the ``on_member_remove`` event listener."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_member: MagicMock,
        mock_guild: MagicMock,
        mock_config_file: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.member = mock_member
        self.guild = mock_guild
        self.member.guild = self.guild

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        welcome_channel = MagicMock(spec=discord.TextChannel)
        welcome_channel.name = "welcome"
        welcome_channel.send = AsyncMock()
        self.welcome_channel = welcome_channel
        self.guild.text_channels = [welcome_channel]

        self.cog = Welcome(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()

    async def test_leave_message_sent(self) -> None:
        """Verify a leave message is sent to the welcome channel."""
        await self.cog.on_member_remove(self.member)
        self.welcome_channel.send.assert_awaited_once()
        call_kwargs = self.welcome_channel.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Left" in embed.title

    async def test_leave_message_includes_member_name(self) -> None:
        """Verify the leave message includes the departing member's name."""
        await self.cog.on_member_remove(self.member)
        call_kwargs = self.welcome_channel.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert str(self.member) in embed.description

    async def test_leave_message_includes_member_count(self) -> None:
        """Verify the leave message shows the new member count."""
        await self.cog.on_member_remove(self.member)
        call_kwargs = self.welcome_channel.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert str(self.guild.member_count) in embed.description

    async def test_no_leave_message_when_channel_missing(self) -> None:
        """Verify no error when the welcome channel does not exist."""
        self.guild.text_channels = []
        await self.cog.on_member_remove(self.member)
        # Should not raise


class TestSetWelcomeCommand:
    """Tests for the /setwelcome slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_config_file: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.config_file = mock_config_file

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        self.cog = Welcome(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()

    async def test_setwelcome_updates_config(self) -> None:
        """Verify /setwelcome writes the new channel name to config.json."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.name = "new-welcome"
        channel.mention = "<#new-welcome>"

        await self.cog.setwelcome.callback(
            self.cog, self.interaction, channel=channel
        )

        # Read back the config file
        updated_cfg = json.loads(self.config_file.read_text())
        assert updated_cfg["welcome_channel"] == "new-welcome"

    async def test_setwelcome_sends_success(self) -> None:
        """Verify the command responds with a success embed."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.name = "announcements"
        channel.mention = "<#announcements>"

        await self.cog.setwelcome.callback(
            self.cog, self.interaction, channel=channel
        )

        self.interaction.response.send_message.assert_awaited_once()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Updated" in embed.title


class TestSetAutoRoleCommand:
    """Tests for the /setautorole slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_config_file: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.config_file = mock_config_file

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        self.cog = Welcome(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()

    async def test_setautorole_updates_config(self) -> None:
        """Verify /setautorole writes the new role name to config.json."""
        role = MagicMock(spec=discord.Role)
        role.name = "Newcomer"

        await self.cog.setautorole.callback(
            self.cog, self.interaction, role=role
        )

        updated_cfg = json.loads(self.config_file.read_text())
        assert updated_cfg["auto_role"] == "Newcomer"

    async def test_setautorole_sends_success(self) -> None:
        """Verify the command responds with a success embed."""
        role = MagicMock(spec=discord.Role)
        role.name = "Verified"

        await self.cog.setautorole.callback(
            self.cog, self.interaction, role=role
        )

        self.interaction.response.send_message.assert_awaited_once()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Updated" in embed.title
        assert "Verified" in embed.description
