"""Tickets cog -- support ticket creation and management via buttons.

Provides a persistent ticket panel with a "Create Ticket" button, per-ticket
control views with a "Close Ticket" button, and slash commands for creating
tickets and sending ticket panels.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot import config
from bot.utils.database import close_ticket, create_ticket, get_open_ticket
from bot.utils.embeds import error_embed, info_embed, success_embed
from bot.utils.permissions import is_admin, on_permission_error

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNSAFE_CHANNEL_CHARS = re.compile(r"[^a-z0-9-]")


def _sanitize_channel_name(name: str) -> str:
    """Convert a username into a valid Discord channel name fragment."""
    sanitized = _UNSAFE_CHANNEL_CHARS.sub("-", name.lower())
    # Collapse multiple consecutive hyphens and strip leading/trailing ones
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
    return sanitized or "unknown"


def _load_config() -> dict[str, Any]:
    """Read the JSON configuration file from disk."""
    with open(config.CONFIG_PATH, encoding="utf-8") as fp:
        return json.load(fp)


# ---------------------------------------------------------------------------
# Persistent views
# ---------------------------------------------------------------------------


class TicketPanelView(discord.ui.View):
    """A persistent view with a single "Create Ticket" button.

    Attached to the ticket panel embed sent by ``/ticket-panel``.  Because
    ``timeout=None`` and every button has a ``custom_id``, Discord will
    re-dispatch interactions even after a bot restart.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create Ticket",
        emoji="\N{ADMISSION TICKETS}",
        style=discord.ButtonStyle.success,
        custom_id="ticket:create",
    )
    async def create_ticket_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[TicketPanelView],
    ) -> None:
        """Handle the *Create Ticket* button press."""
        await _handle_ticket_creation(interaction)


class TicketControlView(discord.ui.View):
    """A persistent view placed inside every ticket channel.

    Contains a single "Close Ticket" button that archives / deletes the
    ticket channel.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close",
    )
    async def close_ticket_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[TicketControlView],
    ) -> None:
        """Handle the *Close Ticket* button press."""
        assert interaction.guild is not None
        assert interaction.channel is not None

        # Mark the ticket as closed in the database
        await close_ticket(interaction.channel.id)

        await interaction.response.send_message(
            embed=info_embed(
                "Ticket Closing",
                "This ticket will be closed in **5 seconds**.",
            ),
        )

        await asyncio.sleep(5)

        # Delete the channel (the ticket itself)
        try:
            assert isinstance(interaction.channel, discord.TextChannel)
            await interaction.channel.delete(reason="Ticket closed")
        except discord.Forbidden:
            log.warning(
                "Missing permissions to delete ticket channel %s in guild %s",
                interaction.channel,
                interaction.guild.name,
            )
        except discord.HTTPException as exc:
            log.error(
                "Failed to delete ticket channel %s: %s",
                interaction.channel,
                exc,
            )


# ---------------------------------------------------------------------------
# Shared ticket-creation logic (used by both button and slash command)
# ---------------------------------------------------------------------------


async def _handle_ticket_creation(interaction: discord.Interaction) -> None:
    """Create a new support ticket for the interacting user.

    This is the shared implementation behind both the panel button and the
    ``/ticket`` slash command.
    """
    assert interaction.guild is not None
    assert isinstance(interaction.user, discord.Member)

    # --- Check for an existing open ticket --------------------------------
    existing = await get_open_ticket(interaction.guild.id, interaction.user.id)
    if existing is not None:
        await interaction.response.send_message(
            embed=error_embed(
                "Ticket Already Open",
                "You already have an open ticket. Please use your existing "
                f"ticket (<#{existing['channel_id']}>) or close it first.",
            ),
            ephemeral=True,
        )
        return

    # --- Locate the ticket category ---------------------------------------
    cfg = _load_config()
    category_name: str = cfg.get("ticket_category", "Support Tickets")
    category = discord.utils.get(interaction.guild.categories, name=category_name)

    if category is None:
        log.warning(
            "Ticket category '%s' not found in guild %s (%s)",
            category_name,
            interaction.guild.name,
            interaction.guild.id,
        )
        await interaction.response.send_message(
            embed=error_embed(
                "Configuration Error",
                f"The ticket category **{category_name}** was not found. "
                "Please ask an administrator to create it.",
            ),
            ephemeral=True,
        )
        return

    # --- Build permission overwrites --------------------------------------
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        interaction.guild.default_role: discord.PermissionOverwrite(
            read_messages=False,
        ),
        interaction.user: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
        ),
    }

    # Allow the bot itself to manage the channel
    if interaction.guild.me is not None:
        overwrites[interaction.guild.me] = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            manage_channels=True,
        )

    # Grant access to moderators (members with Manage Messages permission)
    for role in interaction.guild.roles:
        if role.permissions.manage_messages and not role.is_default():
            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
            )

    # --- Create the channel -----------------------------------------------
    channel_name = f"ticket-{_sanitize_channel_name(interaction.user.name)}"

    try:
        channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Support ticket opened by {interaction.user}",
        )
    except discord.Forbidden:
        log.warning(
            "Missing permissions to create ticket channel in guild %s",
            interaction.guild.name,
        )
        await interaction.response.send_message(
            embed=error_embed(
                "Permission Error",
                "I don't have permission to create channels. "
                "Please ask an administrator to check my role permissions.",
            ),
            ephemeral=True,
        )
        return
    except discord.HTTPException as exc:
        log.error("Failed to create ticket channel: %s", exc)
        await interaction.response.send_message(
            embed=error_embed(
                "Channel Creation Failed",
                "Something went wrong while creating the ticket channel. "
                "Please try again later.",
            ),
            ephemeral=True,
        )
        return

    # --- Persist the ticket in the database --------------------------------
    await create_ticket(
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
        channel_id=channel.id,
    )

    # --- Send the welcome message inside the ticket channel ----------------
    ticket_embed = info_embed(
        "Ticket Opened",
        (
            f"Welcome {interaction.user.mention}!\n\n"
            "Please describe your issue and a staff member will be with you shortly.\n"
            "Click the **Close Ticket** button below when your issue is resolved."
        ),
    )
    ticket_embed.set_footer(text=f"Ticket for {interaction.user} ({interaction.user.id})")

    await channel.send(embed=ticket_embed, view=TicketControlView())

    # --- Confirm to the user (ephemeral) -----------------------------------
    await interaction.response.send_message(
        embed=success_embed(
            "Ticket Created",
            f"Your ticket has been created: {channel.mention}",
        ),
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class Tickets(commands.Cog):
    """Support ticket system with persistent button views."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Persistent view registration
    # ------------------------------------------------------------------

    async def cog_load(self) -> None:
        """Register persistent views so they survive bot restarts."""
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketControlView())

    # ==================================================================
    # Slash commands
    # ==================================================================

    # --- /ticket ------------------------------------------------------

    @app_commands.command(
        name="ticket",
        description="Create a new support ticket",
    )
    async def ticket(self, interaction: discord.Interaction) -> None:
        """Create a support ticket via slash command (alternative to the button)."""
        await _handle_ticket_creation(interaction)

    # --- /ticket-panel ------------------------------------------------

    @app_commands.command(
        name="ticket-panel",
        description="Send a ticket panel with a Create Ticket button",
    )
    @is_admin()
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        """Send a ticket panel embed to the current channel."""
        assert interaction.channel is not None

        # Acknowledge the interaction first (ephemeral confirmation)
        await interaction.response.send_message(
            embed=success_embed(
                "Panel Sent",
                "The ticket panel has been sent to this channel.",
            ),
            ephemeral=True,
        )

        # Then send the panel embed as a regular channel message
        panel_embed = info_embed(
            "Support Tickets",
            (
                "Need help? Click the button below to open a support ticket.\n\n"
                "A private channel will be created for you where you can describe "
                "your issue and communicate with our staff.\n\n"
                "Please do not open multiple tickets for the same issue."
            ),
        )
        panel_embed.set_footer(text="Click the button below to get started")

        await interaction.channel.send(embed=panel_embed, view=TicketPanelView())  # type: ignore[union-attr]

    # ==================================================================
    # Error handler
    # ==================================================================

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle errors raised by slash commands in this cog."""

        # Permission-related errors
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            await on_permission_error(interaction, error)
            return

        # Bot missing permissions
        if isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = error_embed(
                "Bot Missing Permissions",
                f"I need the following permission(s) to do that:\n**{missing}**",
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Unknown -- log and surface a generic message
        log.exception("Unhandled error in tickets cog", exc_info=error)
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
    await bot.add_cog(Tickets(bot))
