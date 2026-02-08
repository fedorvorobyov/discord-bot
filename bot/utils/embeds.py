"""Reusable :class:`discord.Embed` factory helpers.

Every function returns a fully-formed embed so callers can simply do::

    await interaction.response.send_message(embed=success_embed("Done!"))
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord


# ---------------------------------------------------------------------------
# Generic embeds
# ---------------------------------------------------------------------------


def success_embed(title: str, description: str = "") -> discord.Embed:
    """Green embed for successful actions."""
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )


def error_embed(title: str, description: str = "") -> discord.Embed:
    """Red embed for errors."""
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )


def info_embed(title: str, description: str = "") -> discord.Embed:
    """Blue embed for informational messages."""
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )


def warning_embed(title: str, description: str = "") -> discord.Embed:
    """Orange embed for warnings."""
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Specialised embeds
# ---------------------------------------------------------------------------

# Mapping of moderation action keywords to embed colours.
_MOD_ACTION_COLORS: dict[str, discord.Color] = {
    "ban": discord.Color.red(),
    "unban": discord.Color.green(),
    "kick": discord.Color.orange(),
    "mute": discord.Color.orange(),
    "unmute": discord.Color.green(),
    "warn": discord.Color.yellow(),
    "timeout": discord.Color.orange(),
}


def mod_log_embed(
    action: str,
    moderator: discord.Member,
    target: discord.Member | discord.User,
    reason: str = "No reason provided",
) -> discord.Embed:
    """Embed for moderation log entries.

    Parameters
    ----------
    action:
        Human-readable action name, e.g. ``"Member Kicked"``.
    moderator:
        The staff member who performed the action.
    target:
        The member/user the action was performed on.
    reason:
        Optional reason string.
    """
    # Pick a colour based on the action keyword (fall back to grey)
    action_lower = action.lower()
    color = discord.Color.greyple()
    for keyword, col in _MOD_ACTION_COLORS.items():
        if keyword in action_lower:
            color = col
            break

    embed = discord.Embed(
        title=action,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=True)
    embed.add_field(name="Target", value=f"{target} ({target.id})", inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"Moderator ID: {moderator.id} | Target ID: {target.id}")

    return embed


def welcome_embed(member: discord.Member) -> discord.Embed:
    """Embed for welcoming new members.

    Parameters
    ----------
    member:
        The :class:`discord.Member` who just joined.
    """
    guild = member.guild

    embed = discord.Embed(
        title=f"Welcome to {guild.name}!",
        description=f"Hey {member.mention}, welcome to **{guild.name}**! We're glad to have you here.",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )

    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    elif member.default_avatar:
        embed.set_thumbnail(url=member.default_avatar.url)

    embed.add_field(
        name="Member Count",
        value=str(guild.member_count),
        inline=True,
    )

    return embed
