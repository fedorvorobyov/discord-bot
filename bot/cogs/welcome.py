"""Welcome cog -- greet new members and bid farewell to departing ones.

Provides ``on_member_join`` and ``on_member_remove`` listeners as well as
admin-only slash commands to configure the welcome channel and auto-role.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot import config
from bot.utils.embeds import error_embed, info_embed, success_embed, welcome_embed
from bot.utils.permissions import is_admin, on_permission_error

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class Welcome(commands.Cog):
    """Handles member join/leave events and welcome-channel configuration."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config() -> dict[str, Any]:
        """Load the JSON configuration file from disk."""
        with open(config.CONFIG_PATH, encoding="utf-8") as fp:
            return json.load(fp)

    @staticmethod
    def _save_config(data: dict[str, Any]) -> None:
        """Write *data* back to the JSON configuration file."""
        with open(config.CONFIG_PATH, "w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)
            fp.write("\n")

    # ------------------------------------------------------------------
    # Channel lookup helper
    # ------------------------------------------------------------------

    def _get_welcome_channel(
        self,
        guild: discord.Guild,
        cfg: dict[str, Any],
    ) -> discord.TextChannel | None:
        """Return the welcome :class:`TextChannel`, or ``None`` if not found."""
        channel_name: str = cfg.get("welcome_channel", "welcome")
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if channel is None:
            log.warning(
                "Welcome channel '%s' not found in guild %s (%s)",
                channel_name,
                guild.name,
                guild.id,
            )
        return channel

    # ==================================================================
    # Events
    # ==================================================================

    # --- on_member_join -----------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Send a welcome embed and auto-assign a role to new members."""
        guild = member.guild
        cfg = self._load_config()

        # -- Welcome message -------------------------------------------
        channel = self._get_welcome_channel(guild, cfg)
        if channel is not None:
            try:
                await channel.send(embed=welcome_embed(member))
            except discord.Forbidden:
                log.error(
                    "Missing permissions to send welcome message in #%s (guild: %s)",
                    channel.name,
                    guild.id,
                )

        # -- Auto-role -------------------------------------------------
        role_name: str = cfg.get("auto_role", "")
        if not role_name:
            return

        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            log.warning(
                "Auto-role '%s' not found in guild %s (%s)",
                role_name,
                guild.name,
                guild.id,
            )
            return

        try:
            await member.add_roles(role, reason="Auto-role on join")
        except discord.Forbidden:
            log.error(
                "Missing permissions to assign role '%s' to %s in guild %s (%s)",
                role_name,
                member,
                guild.name,
                guild.id,
            )
        except discord.HTTPException as exc:
            log.error(
                "Failed to assign auto-role '%s' to %s: %s",
                role_name,
                member,
                exc,
            )

    # --- on_member_remove ---------------------------------------------

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Send a leave notification when a member leaves the server."""
        guild = member.guild
        cfg = self._load_config()

        channel = self._get_welcome_channel(guild, cfg)
        if channel is None:
            return

        member_count = guild.member_count or 0
        embed = info_embed(
            title="Member Left",
            description=(
                f"**{member}** has left the server.\n"
                f"We now have **{member_count}** member(s)."
            ),
        )

        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        elif member.default_avatar:
            embed.set_thumbnail(url=member.default_avatar.url)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            log.error(
                "Missing permissions to send leave message in #%s (guild: %s)",
                channel.name,
                guild.id,
            )

    # ==================================================================
    # Slash commands
    # ==================================================================

    # --- /setwelcome --------------------------------------------------

    @app_commands.command(
        name="setwelcome",
        description="Set the channel used for welcome and leave messages",
    )
    @app_commands.describe(channel="The text channel to use for welcome messages")
    @is_admin()
    async def setwelcome(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        """Update the ``welcome_channel`` setting in *config.json*."""
        cfg = self._load_config()
        cfg["welcome_channel"] = channel.name
        self._save_config(cfg)

        await interaction.response.send_message(
            embed=success_embed(
                "Welcome Channel Updated",
                f"Welcome messages will now be sent to {channel.mention}.",
            ),
        )

    # --- /setautorole -------------------------------------------------

    @app_commands.command(
        name="setautorole",
        description="Set the role automatically assigned to new members",
    )
    @app_commands.describe(role="The role to assign to every new member")
    @is_admin()
    async def setautorole(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        """Update the ``auto_role`` setting in *config.json*."""
        cfg = self._load_config()
        cfg["auto_role"] = role.name
        self._save_config(cfg)

        await interaction.response.send_message(
            embed=success_embed(
                "Auto-Role Updated",
                f"New members will now receive the **{role.name}** role automatically.",
            ),
        )

    # ==================================================================
    # Error handler
    # ==================================================================

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle errors raised by slash commands in this cog."""
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            await on_permission_error(interaction, error)
            return

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
        log.exception("Unhandled error in welcome cog", exc_info=error)
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
    await bot.add_cog(Welcome(bot))
