"""Permission check decorators for application (slash) commands.

Usage example::

    from bot.utils.permissions import is_moderator, is_admin

    @app_commands.command()
    @is_moderator()
    async def warn(self, interaction: discord.Interaction, ...):
        ...

    @app_commands.command()
    @is_admin()
    async def setup(self, interaction: discord.Interaction, ...):
        ...
"""

from __future__ import annotations

from typing import Callable, TypeVar

import discord
from discord import app_commands

from bot.utils.embeds import error_embed

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Decorator factories
# ---------------------------------------------------------------------------


def is_moderator() -> Callable[[T], T]:
    """Check that the invoking user has at least one moderation permission.

    Passes if the user has **any** of:
    - Manage Messages
    - Kick Members
    - Ban Members

    Raises :exc:`app_commands.MissingPermissions` otherwise.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if perms.manage_messages or perms.kick_members or perms.ban_members:
            return True
        raise app_commands.MissingPermissions(
            ["manage_messages", "kick_members", "ban_members"]
        )

    return app_commands.check(predicate)


def is_admin() -> Callable[[T], T]:
    """Check that the invoking user has the Administrator permission.

    Raises :exc:`app_commands.MissingPermissions` otherwise.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if perms.administrator:
            return True
        raise app_commands.MissingPermissions(["administrator"])

    return app_commands.check(predicate)


# ---------------------------------------------------------------------------
# Error handler helper
# ---------------------------------------------------------------------------


async def on_permission_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    """Respond with a user-friendly embed when a permission check fails.

    Intended to be called from a cog's ``cog_app_command_error`` handler or
    from the bot-wide ``tree.on_error`` callback::

        @bot.tree.error
        async def on_app_command_error(interaction, error):
            await on_permission_error(interaction, error)
    """
    if isinstance(error, app_commands.MissingPermissions):
        missing = ", ".join(error.missing_permissions)
        embed = error_embed(
            title="Permission Denied",
            description=(
                "You don't have permission to use this command.\n"
                f"**Missing:** {missing}"
            ),
        )
    elif isinstance(error, app_commands.CheckFailure):
        embed = error_embed(
            title="Permission Denied",
            description="You don't have permission to use this command.",
        )
    else:
        # Not a permission error -- re-raise so other handlers can catch it.
        raise error

    # Respond (or follow up if the interaction was already acknowledged).
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)
