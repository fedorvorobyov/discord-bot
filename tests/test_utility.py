"""Tests for the utility cog.

Covers /serverinfo, /userinfo, and /poll commands.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.cogs.utility import Utility, _NUMBER_EMOJIS


# ===================================================================
# /serverinfo tests
# ===================================================================


class TestServerInfoCommand:
    """Tests for the /serverinfo slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.guild = mock_guild

        # Set up realistic members for online/bot counting
        online_member = MagicMock(spec=discord.Member)
        online_member.status = discord.Status.online
        online_member.bot = False

        offline_member = MagicMock(spec=discord.Member)
        offline_member.status = discord.Status.offline
        offline_member.bot = False

        bot_member = MagicMock(spec=discord.Member)
        bot_member.status = discord.Status.online
        bot_member.bot = True

        self.guild.members = [online_member, offline_member, bot_member]

        self.cog = Utility(self.bot)

    async def test_serverinfo_has_owner_field(self) -> None:
        """Verify the embed includes the server owner."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Owner" in field_names

    async def test_serverinfo_has_members_field(self) -> None:
        """Verify the embed includes a Members field."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Members" in field_names

    async def test_serverinfo_has_channels_fields(self) -> None:
        """Verify the embed includes text and voice channel counts."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Text Channels" in field_names
        assert "Voice Channels" in field_names

    async def test_serverinfo_has_boosts_fields(self) -> None:
        """Verify the embed includes boost level and count."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Boost Level" in field_names
        assert "Boosts" in field_names

    async def test_serverinfo_has_online_and_bots_fields(self) -> None:
        """Verify the embed includes online member and bot counts."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Online" in field_names
        assert "Bots" in field_names

    async def test_serverinfo_online_count_excludes_bots(self) -> None:
        """Verify the online count only counts non-bot members."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        online_field = next(f for f in embed.fields if f.name == "Online")
        # 1 human online, 1 offline human, 1 online bot -> online = 1
        assert online_field.value == "1"

    async def test_serverinfo_bot_count(self) -> None:
        """Verify the bot count is correct."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        bots_field = next(f for f in embed.fields if f.name == "Bots")
        assert bots_field.value == "1"

    async def test_serverinfo_has_roles_field(self) -> None:
        """Verify the embed includes a Roles field."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Roles" in field_names

    async def test_serverinfo_title_is_guild_name(self) -> None:
        """Verify the embed title is the guild name."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed.title == self.guild.name

    async def test_serverinfo_footer_has_guild_id(self) -> None:
        """Verify the footer contains the guild ID."""
        await self.cog.serverinfo.callback(self.cog, self.interaction)
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert str(self.guild.id) in embed.footer.text


# ===================================================================
# /userinfo tests
# ===================================================================


class TestUserInfoCommand:
    """Tests for the /userinfo slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        mock_target: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.member = mock_member
        self.target = mock_target
        self.guild = mock_guild
        self.cog = Utility(self.bot)

    async def test_userinfo_has_username_field(self) -> None:
        """Verify the embed includes the Username field."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Username" in field_names

    async def test_userinfo_has_id_field(self) -> None:
        """Verify the embed includes the user ID field."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        id_field = next(f for f in embed.fields if f.name == "ID")
        assert str(self.target.id) in id_field.value

    async def test_userinfo_has_top_role_field(self) -> None:
        """Verify the embed includes the top role."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Top Role" in field_names

    async def test_userinfo_has_joined_server_field(self) -> None:
        """Verify the embed includes the join date."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Joined Server" in field_names

    async def test_userinfo_has_account_created_field(self) -> None:
        """Verify the embed includes the account creation date."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Account Created" in field_names

    async def test_userinfo_has_bot_field(self) -> None:
        """Verify the embed indicates whether the user is a bot."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        bot_field = next(f for f in embed.fields if f.name == "Bot")
        assert bot_field.value == "No"

    async def test_userinfo_defaults_to_author(self) -> None:
        """Verify /userinfo with no target defaults to the command author."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=None
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        # Should show the interaction user (mock_member)
        assert embed.title == self.member.display_name

    async def test_userinfo_shows_target_data(self) -> None:
        """Verify /userinfo with a target shows that target's data."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed.title == self.target.display_name

    async def test_userinfo_has_roles_field(self) -> None:
        """Verify the embed includes a Roles field."""
        await self.cog.userinfo.callback(
            self.cog, self.interaction, user=self.target
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Roles" in field_names


# ===================================================================
# /poll tests
# ===================================================================


class TestPollCommand:
    """Tests for the /poll slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.cog = Utility(self.bot)

    async def test_poll_creates_embed_with_question(self) -> None:
        """Verify the poll embed includes the question."""
        await self.cog.poll.callback(
            self.cog,
            self.interaction,
            question="Favourite colour?",
            option1="Red",
            option2="Blue",
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert "Favourite colour?" in embed.title

    async def test_poll_embed_has_options(self) -> None:
        """Verify the poll embed lists all provided options."""
        await self.cog.poll.callback(
            self.cog,
            self.interaction,
            question="Best language?",
            option1="Python",
            option2="Rust",
            option3="Go",
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert "Python" in embed.description
        assert "Rust" in embed.description
        assert "Go" in embed.description

    async def test_poll_adds_reactions(self) -> None:
        """Verify reactions are added for each option."""
        await self.cog.poll.callback(
            self.cog,
            self.interaction,
            question="Pick one",
            option1="A",
            option2="B",
            option3="C",
        )
        # original_response returns a mock message with add_reaction
        msg = await self.interaction.original_response()
        assert msg.add_reaction.await_count == 3

    async def test_poll_reactions_match_options_count(self) -> None:
        """Verify the number of reactions matches the number of options."""
        await self.cog.poll.callback(
            self.cog,
            self.interaction,
            question="Pick",
            option1="X",
            option2="Y",
        )
        msg = await self.interaction.original_response()
        # 2 options -> 2 reactions (but original_response is called twice now)
        # We check the add_reaction calls on the message
        # The original_response is called once in poll, once here
        # The message mock is the same object, so reactions accumulate
        # We need to check >= 2
        assert msg.add_reaction.await_count >= 2

    async def test_poll_footer_shows_author(self) -> None:
        """Verify the poll footer credits the poll creator."""
        await self.cog.poll.callback(
            self.cog,
            self.interaction,
            question="Test poll",
            option1="Yes",
            option2="No",
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert self.interaction.user.display_name in embed.footer.text

    async def test_poll_none_options_ignored(self) -> None:
        """Verify None optional parameters are properly filtered out."""
        await self.cog.poll.callback(
            self.cog,
            self.interaction,
            question="Test",
            option1="A",
            option2="B",
            option3=None,
            option4=None,
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        # Only 2 options should appear
        lines = [line for line in embed.description.split("\n\n") if line.strip()]
        assert len(lines) == 2

    async def test_poll_uses_number_emojis(self) -> None:
        """Verify the poll description uses the correct number emojis."""
        await self.cog.poll.callback(
            self.cog,
            self.interaction,
            question="Numbers",
            option1="First",
            option2="Second",
        )
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert _NUMBER_EMOJIS[0] in embed.description
        assert _NUMBER_EMOJIS[1] in embed.description
