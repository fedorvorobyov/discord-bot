"""Tests for the tickets cog.

Covers ticket creation, duplicate prevention, ticket closing, and the
ticket panel slash command.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot import config
from bot.cogs.tickets import Tickets, TicketControlView, TicketPanelView, _handle_ticket_creation
from bot.utils.database import close_ticket, create_ticket, get_open_ticket


class TestTicketCreation:
    """Tests for the ticket creation flow."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_config_file: MagicMock,
        setup_database: None,
        tmp_path: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.guild = mock_guild

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        self._db_patch = patch.object(
            config, "DATABASE_PATH", str(tmp_path / "test_bot.db")
        )
        self._db_patch.start()

        # Create a ticket category in the guild
        category = MagicMock(spec=discord.CategoryChannel)
        category.name = "Support Tickets"
        self.guild.categories = [category]

        # Mock create_text_channel to return a new channel
        ticket_channel = MagicMock(spec=discord.TextChannel)
        ticket_channel.id = 600000000000000000
        ticket_channel.name = "ticket-testuser"
        ticket_channel.mention = "<#600000000000000000>"
        ticket_channel.send = AsyncMock()
        ticket_channel.delete = AsyncMock()
        self.ticket_channel = ticket_channel
        self.guild.create_text_channel = AsyncMock(return_value=ticket_channel)

        # Make sure the mod roles check works
        for role in self.guild.roles:
            role.is_default = MagicMock(return_value=(role == self.guild.default_role))

        self.cog = Tickets(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()
        self._db_patch.stop()

    async def test_ticket_creates_channel(self) -> None:
        """Verify a text channel is created for the ticket."""
        await _handle_ticket_creation(self.interaction)
        self.guild.create_text_channel.assert_awaited_once()

    async def test_ticket_saves_db_record(self) -> None:
        """Verify the ticket is saved to the database."""
        await _handle_ticket_creation(self.interaction)

        ticket = await get_open_ticket(
            self.interaction.guild.id,
            self.interaction.user.id,
        )
        assert ticket is not None
        assert ticket["channel_id"] == self.ticket_channel.id
        assert ticket["status"] == "open"

    async def test_ticket_sends_welcome_in_channel(self) -> None:
        """Verify a welcome message is posted in the new ticket channel."""
        await _handle_ticket_creation(self.interaction)
        self.ticket_channel.send.assert_awaited_once()
        call_kwargs = self.ticket_channel.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Ticket Opened" in embed.title

    async def test_ticket_sends_confirmation_to_user(self) -> None:
        """Verify the user gets an ephemeral confirmation."""
        await _handle_ticket_creation(self.interaction)
        self.interaction.response.send_message.assert_awaited()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Created" in embed.title

    async def test_ticket_channel_has_control_view(self) -> None:
        """Verify the ticket channel message includes a TicketControlView."""
        await _handle_ticket_creation(self.interaction)
        call_kwargs = self.ticket_channel.send.call_args
        view = call_kwargs.kwargs.get("view")
        assert isinstance(view, TicketControlView)


class TestDuplicateTicketPrevention:
    """Tests for preventing duplicate open tickets."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_config_file: MagicMock,
        setup_database: None,
        tmp_path: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.guild = mock_guild

        self._config_patch = patch.object(
            config, "CONFIG_PATH", str(mock_config_file)
        )
        self._config_patch.start()

        self._db_patch = patch.object(
            config, "DATABASE_PATH", str(tmp_path / "test_bot.db")
        )
        self._db_patch.start()

        # Create a ticket category
        category = MagicMock(spec=discord.CategoryChannel)
        category.name = "Support Tickets"
        self.guild.categories = [category]

        ticket_channel = MagicMock(spec=discord.TextChannel)
        ticket_channel.id = 600000000000000001
        ticket_channel.name = "ticket-testuser"
        ticket_channel.mention = "<#600000000000000001>"
        ticket_channel.send = AsyncMock()
        self.guild.create_text_channel = AsyncMock(return_value=ticket_channel)

        for role in self.guild.roles:
            role.is_default = MagicMock(return_value=(role == self.guild.default_role))

        self.cog = Tickets(self.bot)

    def teardown_method(self) -> None:
        self._config_patch.stop()
        self._db_patch.stop()

    async def test_duplicate_ticket_shows_error(self) -> None:
        """Verify an error is returned when user already has an open ticket."""
        # Create an existing open ticket in the DB
        await create_ticket(
            guild_id=self.interaction.guild.id,
            user_id=self.interaction.user.id,
            channel_id=700000000000000000,
        )

        await _handle_ticket_creation(self.interaction)

        # Should NOT create a second channel
        self.guild.create_text_channel.assert_not_awaited()

        # Should respond with an error
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Already Open" in embed.title


class TestTicketClose:
    """Tests for closing a ticket."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
        mock_text_channel: MagicMock,
        setup_database: None,
        tmp_path: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.channel = mock_text_channel
        self.interaction.channel = self.channel

        self._db_patch = patch.object(
            config, "DATABASE_PATH", str(tmp_path / "test_bot.db")
        )
        self._db_patch.start()

    def teardown_method(self) -> None:
        self._db_patch.stop()

    async def test_close_ticket_updates_db(self) -> None:
        """Verify closing a ticket marks it as 'closed' in the database."""
        # Create a ticket record
        ticket_id = await create_ticket(
            guild_id=self.interaction.guild.id,
            user_id=self.interaction.user.id,
            channel_id=self.channel.id,
        )

        # Close it
        await close_ticket(self.channel.id)

        # Verify the ticket is no longer open
        open_ticket = await get_open_ticket(
            self.interaction.guild.id,
            self.interaction.user.id,
        )
        assert open_ticket is None

    async def test_close_ticket_button_responds(self) -> None:
        """Verify the close button sends a closing message."""
        # Create ticket in DB
        await create_ticket(
            guild_id=self.interaction.guild.id,
            user_id=self.interaction.user.id,
            channel_id=self.channel.id,
        )

        view = TicketControlView()

        # Patch asyncio.sleep to avoid the 5-second wait
        with patch("bot.cogs.tickets.asyncio.sleep", new_callable=AsyncMock):
            await view.close_ticket_button.callback(self.interaction)

        # Verify the response was sent
        self.interaction.response.send_message.assert_awaited_once()
        call_kwargs = self.interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert "Closing" in embed.title

    async def test_close_ticket_button_deletes_channel(self) -> None:
        """Verify the close button deletes the ticket channel."""
        await create_ticket(
            guild_id=self.interaction.guild.id,
            user_id=self.interaction.user.id,
            channel_id=self.channel.id,
        )

        view = TicketControlView()

        with patch("bot.cogs.tickets.asyncio.sleep", new_callable=AsyncMock):
            await view.close_ticket_button.callback(self.interaction)

        self.channel.delete.assert_awaited_once_with(reason="Ticket closed")


class TestTicketPanelCommand:
    """Tests for the /ticket-panel slash command."""

    @pytest.fixture(autouse=True)
    def _setup(
        self,
        mock_bot: MagicMock,
        mock_interaction: MagicMock,
    ) -> None:
        self.bot = mock_bot
        self.interaction = mock_interaction
        self.cog = Tickets(self.bot)

    async def test_ticket_panel_sends_embed(self) -> None:
        """Verify /ticket-panel sends a panel embed to the channel."""
        await self.cog.ticket_panel.callback(self.cog, self.interaction)

        # The channel should receive the panel message
        self.interaction.channel.send.assert_awaited_once()
        call_kwargs = self.interaction.channel.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "Support Tickets" in embed.title

    async def test_ticket_panel_has_button_view(self) -> None:
        """Verify the panel message includes a TicketPanelView."""
        await self.cog.ticket_panel.callback(self.cog, self.interaction)

        call_kwargs = self.interaction.channel.send.call_args
        view = call_kwargs.kwargs.get("view")
        assert isinstance(view, TicketPanelView)

    async def test_ticket_panel_confirms_ephemerally(self) -> None:
        """Verify the admin gets an ephemeral confirmation."""
        await self.cog.ticket_panel.callback(self.cog, self.interaction)

        self.interaction.response.send_message.assert_awaited_once()
        call_kwargs = self.interaction.response.send_message.call_args
        assert call_kwargs.kwargs.get("ephemeral") is True
        embed = call_kwargs.kwargs.get("embed")
        assert "Panel Sent" in embed.title
