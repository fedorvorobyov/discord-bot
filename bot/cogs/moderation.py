"""Moderation cog -- kick, ban, mute, purge, warn, and auto-moderation.

Provides slash commands that require moderator permissions and an
``on_message`` listener for word-filter and spam-detection auto-moderation.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from datetime import timedelta
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot import config
from bot.utils.database import add_warning, get_warning_count, get_warnings
from bot.utils.embeds import (
    error_embed,
    info_embed,
    mod_log_embed,
    success_embed,
    warning_embed,
)
from bot.utils.permissions import is_moderator, on_permission_error

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Duration parser  (e.g. "10m", "1h", "1d", "30s")
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$", re.IGNORECASE)

_DURATION_UNITS: dict[str, str] = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
}

_MAX_TIMEOUT = timedelta(days=28)


def _parse_duration(raw: str) -> timedelta | None:
    """Parse a human-friendly duration string into a :class:`timedelta`.

    Accepted formats: ``30s``, ``10m``, ``1h``, ``7d``.
    Returns ``None`` if the string cannot be parsed.
    """
    match = _DURATION_RE.match(raw.strip())
    if match is None:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    return timedelta(**{_DURATION_UNITS[unit]: value})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Spam-tracking data structure
# ---------------------------------------------------------------------------


class _MessageRecord:
    """Tracks recent messages for a single guild member."""

    __slots__ = ("messages",)

    def __init__(self) -> None:
        # list of (content, timestamp) pairs
        self.messages: list[tuple[str, float]] = []

    def add(self, content: str, now: float) -> None:
        self.messages.append((content, now))

    def prune(self, cutoff: float) -> None:
        """Remove entries older than *cutoff*."""
        self.messages = [(c, t) for c, t in self.messages if t >= cutoff]

    def identical_count(self, content: str) -> int:
        """Return how many stored messages are identical to *content*."""
        return sum(1 for c, _ in self.messages if c == content)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class Moderation(commands.Cog):
    """Slash-command moderation suite and auto-moderation listeners."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Load config.json once at init; reload on cog_load if needed.
        self._config: dict[str, Any] = self._load_config()

        # In-memory spam tracker:  {(guild_id, user_id): _MessageRecord}
        self._spam_tracker: defaultdict[tuple[int, int], _MessageRecord] = defaultdict(
            _MessageRecord,
        )

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config() -> dict[str, Any]:
        with open(config.CONFIG_PATH, encoding="utf-8") as fp:
            return json.load(fp)

    # ------------------------------------------------------------------
    # Mod-log helper
    # ------------------------------------------------------------------

    async def _send_mod_log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        """Find the configured mod-log channel and send *embed* to it."""
        channel_name: str = self._config.get("mod_log_channel", "mod-log")
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if channel is None:
            log.warning(
                "Mod-log channel '%s' not found in guild %s (%s)",
                channel_name,
                guild.name,
                guild.id,
            )
            return
        await channel.send(embed=embed)

    # ------------------------------------------------------------------
    # Hierarchy check
    # ------------------------------------------------------------------

    @staticmethod
    def _can_action_member(
        guild: discord.Guild,
        target: discord.Member,
    ) -> bool:
        """Return ``True`` if the bot's top role is above *target*'s top role."""
        assert guild.me is not None
        return guild.me.top_role > target.top_role

    # ==================================================================
    # Slash commands
    # ==================================================================

    # --- /kick --------------------------------------------------------

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(
        member="The member to kick",
        reason="Reason for the kick",
    )
    @is_moderator()
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        if not self._can_action_member(interaction.guild, member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Cannot Kick",
                    "That member has a higher or equal role than me.",
                ),
                ephemeral=True,
            )
            return

        # DM the user before kicking (best-effort)
        try:
            await member.send(
                embed=warning_embed(
                    "You have been kicked",
                    f"You were kicked from **{interaction.guild.name}**.\n**Reason:** {reason}",
                ),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        await member.kick(reason=reason)

        # Mod-log
        log_embed = mod_log_embed(
            action="Member Kicked",
            moderator=interaction.user,
            target=member,
            reason=reason,
        )
        await self._send_mod_log(interaction.guild, log_embed)

        # Success reply
        await interaction.response.send_message(
            embed=success_embed(
                "Member Kicked",
                f"{member} has been kicked.\n**Reason:** {reason}",
            ),
        )

    # --- /ban ---------------------------------------------------------

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
    )
    @is_moderator()
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        if not self._can_action_member(interaction.guild, member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Cannot Ban",
                    "That member has a higher or equal role than me.",
                ),
                ephemeral=True,
            )
            return

        # DM the user before banning (best-effort)
        try:
            await member.send(
                embed=warning_embed(
                    "You have been banned",
                    f"You were banned from **{interaction.guild.name}**.\n**Reason:** {reason}",
                ),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        await member.ban(reason=reason)

        # Mod-log
        log_embed = mod_log_embed(
            action="Member Banned",
            moderator=interaction.user,
            target=member,
            reason=reason,
        )
        await self._send_mod_log(interaction.guild, log_embed)

        # Success reply
        await interaction.response.send_message(
            embed=success_embed(
                "Member Banned",
                f"{member} has been banned.\n**Reason:** {reason}",
            ),
        )

    # --- /mute --------------------------------------------------------

    @app_commands.command(
        name="mute",
        description="Timeout (mute) a member for a given duration",
    )
    @app_commands.describe(
        member="The member to mute",
        duration='Duration string, e.g. "10m", "1h", "1d", "30s" (max 28d)',
    )
    @is_moderator()
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
    ) -> None:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        if not self._can_action_member(interaction.guild, member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Cannot Mute",
                    "That member has a higher or equal role than me.",
                ),
                ephemeral=True,
            )
            return

        delta = _parse_duration(duration)
        if delta is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Duration",
                    'Please use a format like `30s`, `10m`, `1h`, or `7d`.',
                ),
                ephemeral=True,
            )
            return

        if delta > _MAX_TIMEOUT:
            await interaction.response.send_message(
                embed=error_embed(
                    "Duration Too Long",
                    "Discord limits timeouts to a maximum of **28 days**.",
                ),
                ephemeral=True,
            )
            return

        await member.timeout(delta, reason=f"Muted by {interaction.user}")

        # Mod-log
        log_embed = mod_log_embed(
            action="Member Muted",
            moderator=interaction.user,
            target=member,
            reason=f"Duration: {duration}",
        )
        await self._send_mod_log(interaction.guild, log_embed)

        # Success reply
        await interaction.response.send_message(
            embed=success_embed(
                "Member Muted",
                f"{member.mention} has been timed out for **{duration}**.",
            ),
        )

    # --- /purge --------------------------------------------------------

    @app_commands.command(
        name="purge",
        description="Delete the last N messages from this channel",
    )
    @app_commands.describe(count="Number of messages to delete (1-100)")
    @is_moderator()
    async def purge(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 100],
    ) -> None:
        assert interaction.channel is not None
        assert isinstance(interaction.channel, discord.TextChannel)

        # Defer ephemerally so the purge can take a moment
        await interaction.response.defer(ephemeral=True)

        deleted = await interaction.channel.purge(limit=count)

        await interaction.followup.send(
            embed=success_embed(
                "Messages Purged",
                f"Successfully deleted **{len(deleted)}** message(s).",
            ),
            ephemeral=True,
        )

    # --- /warn --------------------------------------------------------

    @app_commands.command(name="warn", description="Issue a warning to a member")
    @app_commands.describe(
        member="The member to warn",
        reason="Reason for the warning",
    )
    @is_moderator()
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        # Persist warning
        await add_warning(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            reason=reason,
        )

        total = await get_warning_count(interaction.guild.id, member.id)

        # DM the user (best-effort)
        try:
            await member.send(
                embed=warning_embed(
                    "You have been warned",
                    (
                        f"You received a warning in **{interaction.guild.name}**.\n"
                        f"**Reason:** {reason}\n"
                        f"**Total warnings:** {total}"
                    ),
                ),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Mod-log
        log_embed = mod_log_embed(
            action="Member Warned",
            moderator=interaction.user,
            target=member,
            reason=reason,
        )
        await self._send_mod_log(interaction.guild, log_embed)

        # Success reply
        await interaction.response.send_message(
            embed=success_embed(
                "Member Warned",
                (
                    f"{member.mention} has been warned.\n"
                    f"**Reason:** {reason}\n"
                    f"**Total warnings:** {total}"
                ),
            ),
        )

    # --- /warnings ----------------------------------------------------

    @app_commands.command(
        name="warnings",
        description="View all warnings for a member",
    )
    @app_commands.describe(member="The member whose warnings to view")
    @is_moderator()
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        assert interaction.guild is not None

        records = await get_warnings(interaction.guild.id, member.id)

        if not records:
            await interaction.response.send_message(
                embed=info_embed(
                    "No Warnings",
                    f"{member.mention} has no warnings on record.",
                ),
                ephemeral=True,
            )
            return

        lines: list[str] = []
        for idx, record in enumerate(records, start=1):
            mod = interaction.guild.get_member(record["moderator_id"])
            mod_display = str(mod) if mod else f"Unknown (ID: {record['moderator_id']})"
            lines.append(
                f"**{idx}.** {record['reason']}\n"
                f"   Moderator: {mod_display} | "
                f"Date: {record['created_at']}"
            )

        embed = info_embed(
            title=f"Warnings for {member}",
            description="\n\n".join(lines),
        )
        embed.set_footer(text=f"Total: {len(records)} warning(s)")

        await interaction.response.send_message(embed=embed, ephemeral=True)

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

        # Member not found (wrapped in CommandInvokeError)
        original = getattr(error, "original", error)
        if isinstance(original, discord.NotFound):
            embed = error_embed(
                "Member Not Found",
                "I couldn't find that member in this server.",
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Unknown -- log and surface a generic message
        log.exception("Unhandled error in moderation cog", exc_info=error)
        embed = error_embed(
            "Unexpected Error",
            "Something went wrong. Please try again later.",
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==================================================================
    # Auto-moderation listener
    # ==================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Check every message for filtered words and spam patterns."""
        # Ignore bots and DMs
        if message.author.bot or message.guild is None:
            return

        # Ignore members with moderation permissions (moderators are exempt)
        assert isinstance(message.author, discord.Member)
        perms = message.author.guild_permissions
        if perms.manage_messages or perms.kick_members or perms.ban_members:
            return

        # --- Word filter --------------------------------------------------
        word_filter: list[str] = self._config.get("word_filter", [])
        if word_filter:
            content_lower = message.content.lower()
            for word in word_filter:
                if word.lower() in content_lower:
                    await self._handle_word_filter(message, word)
                    return  # one action per message is enough

        # --- Spam detection -----------------------------------------------
        await self._handle_spam_detection(message)

    # ------------------------------------------------------------------
    # Auto-mod helpers
    # ------------------------------------------------------------------

    async def _handle_word_filter(
        self,
        message: discord.Message,
        matched_word: str,
    ) -> None:
        """Delete the message and send a temporary warning."""
        try:
            await message.delete()
        except discord.Forbidden:
            log.warning(
                "Missing permissions to delete message %s in %s",
                message.id,
                message.channel,
            )
            return

        assert isinstance(message.channel, discord.abc.Messageable)
        warn_msg = await message.channel.send(
            embed=warning_embed(
                "Message Removed",
                f"{message.author.mention}, your message was removed for containing a filtered word.",
            ),
        )

        # Auto-delete the warning after 5 seconds
        await warn_msg.delete(delay=5)

    async def _handle_spam_detection(self, message: discord.Message) -> None:
        """Track message frequency and timeout spammers."""
        assert message.guild is not None
        assert isinstance(message.author, discord.Member)

        threshold: int = self._config.get("spam_threshold", 5)
        interval: int = self._config.get("spam_interval", 10)

        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        record = self._spam_tracker[key]
        record.prune(now - interval)
        record.add(message.content, now)

        if record.identical_count(message.content) >= threshold:
            # Purge the spam from the channel (best-effort)
            try:
                await message.channel.purge(  # type: ignore[union-attr]
                    limit=threshold + 5,
                    check=lambda m: m.author.id == message.author.id,
                )
            except discord.Forbidden:
                pass

            # Timeout the user for 5 minutes
            try:
                await message.author.timeout(
                    timedelta(minutes=5),
                    reason="Auto-moderation: spam detected",
                )
            except discord.Forbidden:
                log.warning(
                    "Missing permissions to timeout %s in %s",
                    message.author,
                    message.guild.name,
                )

            # Notify the channel
            warn_msg = await message.channel.send(
                embed=warning_embed(
                    "Spam Detected",
                    (
                        f"{message.author.mention} has been timed out for **5 minutes** "
                        f"for sending repeated messages."
                    ),
                ),
            )
            await warn_msg.delete(delay=5)

            # Reset the tracker for this user
            del self._spam_tracker[key]


# ---------------------------------------------------------------------------
# Extension setup
# ---------------------------------------------------------------------------


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
