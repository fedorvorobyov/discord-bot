"""Reaction-role cog -- self-assignable roles via emoji reactions.

Provides slash commands for creating and deleting reaction-role menus, and
raw-event listeners that grant or revoke roles when members add or remove
reactions on tracked messages.
"""

from __future__ import annotations

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.database import add_role_menu, delete_role_menu, get_role_menu_by_message
from bot.utils.embeds import error_embed, info_embed, success_embed
from bot.utils.permissions import is_admin, on_permission_error

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping parser
# ---------------------------------------------------------------------------

# Matches a role mention (<@&123456>) preceded by an emoji token.
# The emoji token can be:
#   - A unicode emoji (one or more non-whitespace, non-< characters)
#   - A custom Discord emoji (<:name:id> or <a:name:id>)
_PAIR_RE = re.compile(
    r"(<a?:\w+:\d+>|[^\s<]+)"  # emoji (custom or unicode)
    r"\s+"                      # whitespace separator
    r"<@&(\d+)>",              # role mention -> captures role ID
)


def _parse_mappings(text: str) -> list[tuple[str, int]]:
    """Parse a mappings string into ``(emoji, role_id)`` pairs.

    Expected input format::

        "🎮 @Gamer 🎵 @Music 🎨 @Art"

    Where ``@Gamer`` etc. are role mentions (rendered as ``<@&ID>`` in the
    raw text Discord sends).

    Returns an empty list if nothing could be parsed.
    """
    return [(emoji, int(role_id)) for emoji, role_id in _PAIR_RE.findall(text)]


def _emoji_key(emoji: discord.PartialEmoji | str) -> str:
    """Normalise an emoji to the string key stored in the database.

    For unicode emoji this is just the character(s).  For custom emoji this
    returns the ``<:name:id>`` or ``<a:name:id>`` format.
    """
    if isinstance(emoji, str):
        return emoji
    if emoji.id is not None:
        prefix = "a" if emoji.animated else ""
        return f"<{prefix}:{emoji.name}:{emoji.id}>"
    # Unicode emoji stored on a PartialEmoji
    return emoji.name or ""


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class Roles(commands.Cog):
    """Reaction-role menus: admins create menus, members click to self-assign."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ==================================================================
    # Slash commands
    # ==================================================================

    # --- /rolemenu ----------------------------------------------------

    @app_commands.command(
        name="rolemenu",
        description="Create a reaction-role menu in this channel",
    )
    @app_commands.describe(
        title="Title for the role-menu embed",
        mappings='Emoji-role pairs, e.g. "🎮 @Gamer 🎵 @Music 🎨 @Art"',
    )
    @is_admin()
    async def rolemenu(
        self,
        interaction: discord.Interaction,
        title: str,
        mappings: str,
    ) -> None:
        assert interaction.guild is not None
        assert interaction.channel is not None

        # Parse the raw mappings string
        pairs = _parse_mappings(mappings)

        if not pairs:
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Mappings",
                    (
                        "Could not parse any emoji-role pairs.\n"
                        "Use the format: `🎮 @Gamer 🎵 @Music 🎨 @Art`\n"
                        "Make sure each emoji is followed by a **role mention**."
                    ),
                ),
                ephemeral=True,
            )
            return

        # Build the description listing each emoji -> role
        lines: list[str] = []
        for emoji, role_id in pairs:
            role = interaction.guild.get_role(role_id)
            role_display = role.mention if role else f"<@&{role_id}>"
            lines.append(f"{emoji}  {role_display}")

        description = "React to assign yourself a role!\n\n" + "\n".join(lines)

        embed = info_embed(title=title, description=description)

        # Defer so we can send the embed as a normal (non-ephemeral) message
        await interaction.response.defer(ephemeral=True)

        # Send the role-menu embed to the channel
        assert isinstance(interaction.channel, discord.abc.Messageable)
        menu_message = await interaction.channel.send(embed=embed)

        # Add each emoji as a reaction
        for emoji, _ in pairs:
            try:
                await menu_message.add_reaction(emoji)
            except discord.HTTPException:
                log.warning("Failed to add reaction %s to message %s", emoji, menu_message.id)

        # Persist every mapping to the database
        for emoji, role_id in pairs:
            await add_role_menu(
                guild_id=interaction.guild.id,
                channel_id=menu_message.channel.id,
                message_id=menu_message.id,
                emoji=emoji,
                role_id=role_id,
            )

        await interaction.followup.send(
            embed=success_embed(
                "Role Menu Created",
                (
                    f"Role menu **{title}** has been created with "
                    f"**{len(pairs)}** role(s).\n"
                    f"Message ID: `{menu_message.id}`"
                ),
            ),
            ephemeral=True,
        )

    # --- /delrolemenu -------------------------------------------------

    @app_commands.command(
        name="delrolemenu",
        description="Delete a reaction-role menu by its message ID",
    )
    @app_commands.describe(message_id="The message ID of the role menu to delete")
    @is_admin()
    async def delrolemenu(
        self,
        interaction: discord.Interaction,
        message_id: str,
    ) -> None:
        # Validate that the provided value is a valid integer (message ID)
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Message ID",
                    "Please provide a valid message ID (a number).",
                ),
                ephemeral=True,
            )
            return

        # Check that the message actually has role-menu entries
        existing = await get_role_menu_by_message(msg_id)
        if not existing:
            await interaction.response.send_message(
                embed=error_embed(
                    "Not Found",
                    f"No role menu found for message ID `{msg_id}`.",
                ),
                ephemeral=True,
            )
            return

        await delete_role_menu(msg_id)

        await interaction.response.send_message(
            embed=success_embed(
                "Role Menu Deleted",
                f"All role mappings for message `{msg_id}` have been removed.",
            ),
            ephemeral=True,
        )

    # ==================================================================
    # Reaction events (raw for persistence across restarts)
    # ==================================================================

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Grant a role when a member reacts on a role-menu message."""
        await self._handle_reaction(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Revoke a role when a member removes their reaction from a role-menu message."""
        await self._handle_reaction(payload, add=False)

    # ------------------------------------------------------------------
    # Shared handler
    # ------------------------------------------------------------------

    async def _handle_reaction(
        self,
        payload: discord.RawReactionActionEvent,
        *,
        add: bool,
    ) -> None:
        """Process a reaction add/remove event against the role-menu database."""

        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:  # type: ignore[union-attr]
            return

        # Ignore DMs
        if payload.guild_id is None:
            return

        # Look up role-menu mappings for this message
        mappings = await get_role_menu_by_message(payload.message_id)
        if not mappings:
            return

        # Determine the emoji key to compare against DB entries
        key = _emoji_key(payload.emoji)

        # Find the matching role_id
        role_id: int | None = None
        for mapping in mappings:
            if mapping["emoji"] == key:
                role_id = mapping["role_id"]
                break

        if role_id is None:
            return

        # Resolve guild and member
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        # For reaction remove events the member is not included in the
        # payload, so we must fetch it ourselves.
        if add and payload.member is not None:
            member = payload.member
        else:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.NotFound:
                return

        role = guild.get_role(role_id)
        if role is None:
            log.warning(
                "Role %s not found in guild %s for role menu on message %s",
                role_id,
                guild.id,
                payload.message_id,
            )
            return

        try:
            if add:
                await member.add_roles(role, reason="Reaction role menu")
                log.info(
                    "Granted role %s (%s) to %s (%s) in %s",
                    role.name,
                    role.id,
                    member,
                    member.id,
                    guild.name,
                )
            else:
                await member.remove_roles(role, reason="Reaction role menu")
                log.info(
                    "Removed role %s (%s) from %s (%s) in %s",
                    role.name,
                    role.id,
                    member,
                    member.id,
                    guild.name,
                )
        except discord.Forbidden:
            log.warning(
                "Missing permissions to %s role %s (%s) for %s in %s",
                "add" if add else "remove",
                role.name,
                role.id,
                member,
                guild.name,
            )
        except discord.HTTPException:
            log.exception(
                "HTTP error while updating role %s (%s) for %s in %s",
                role.name,
                role.id,
                member,
                guild.name,
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
        log.exception("Unhandled error in roles cog", exc_info=error)
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
    await bot.add_cog(Roles(bot))
