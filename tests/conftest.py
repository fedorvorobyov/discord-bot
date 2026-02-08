"""Shared pytest fixtures for the Discord bot test suite.

Provides mock Discord objects (bot, guild, member, channel, interaction) and
an in-memory SQLite database fixture so that every test runs in isolation
without touching the real filesystem or network.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest
import pytest_asyncio
from discord.ext import commands

from bot import config
from bot.utils.database import init_db


# ---------------------------------------------------------------------------
# Bot fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_bot() -> MagicMock:
    """Return a mock ``commands.Bot`` with commonly used attributes."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock(spec=discord.User)
    bot.user.id = 100000000000000000
    bot.user.name = "TestBot"
    bot.user.__str__ = lambda self: "TestBot#0001"
    bot.tree = MagicMock()
    bot.add_view = MagicMock()
    return bot


# ---------------------------------------------------------------------------
# Guild fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_guild() -> MagicMock:
    """Return a mock ``discord.Guild`` with sensible defaults."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 200000000000000000
    guild.name = "Test Guild"
    guild.member_count = 42
    guild.premium_tier = 2
    guild.premium_subscription_count = 7
    guild.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    guild.icon = MagicMock()
    guild.icon.url = "https://example.com/icon.png"

    # Owner
    owner = MagicMock(spec=discord.Member)
    owner.mention = "<@111>"
    guild.owner = owner

    # Channels
    text_channel = MagicMock(spec=discord.TextChannel)
    text_channel.name = "general"
    text_channel.id = 300000000000000001
    guild.text_channels = [text_channel]
    guild.voice_channels = [MagicMock(spec=discord.VoiceChannel)]

    # Roles
    default_role = MagicMock(spec=discord.Role)
    default_role.name = "@everyone"
    default_role.is_default = MagicMock(return_value=True)
    default_role.permissions = MagicMock()
    default_role.permissions.manage_messages = False
    guild.default_role = default_role
    guild.roles = [default_role]

    # Bot member
    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock(spec=discord.Role)
    bot_member.top_role.position = 10
    bot_member.top_role.__gt__ = lambda self, other: self.position > other.position
    bot_member.top_role.__lt__ = lambda self, other: self.position < other.position
    guild.me = bot_member

    # Members list (for serverinfo online/bot counting)
    guild.members = []

    # Categories
    guild.categories = []

    return guild


# ---------------------------------------------------------------------------
# Member fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_member(mock_guild: MagicMock) -> MagicMock:
    """Return a mock ``discord.Member`` attached to ``mock_guild``."""
    member = MagicMock(spec=discord.Member)
    member.id = 400000000000000000
    member.name = "testuser"
    member.display_name = "Test User"
    member.mention = "<@400000000000000000>"
    member.bot = False
    member.__str__ = lambda self: "testuser"

    member.guild = mock_guild

    # Permissions — moderator by default
    perms = MagicMock(spec=discord.Permissions)
    perms.manage_messages = True
    perms.kick_members = True
    perms.ban_members = True
    perms.administrator = True
    member.guild_permissions = perms

    # Roles
    top_role = MagicMock(spec=discord.Role)
    top_role.position = 5
    top_role.name = "Moderator"
    top_role.mention = "<@&role_mod>"
    top_role.color = discord.Color.blue()
    top_role.__gt__ = lambda self, other: self.position > other.position
    top_role.__lt__ = lambda self, other: self.position < other.position
    top_role.__eq__ = lambda self, other: self.position == other.position
    top_role.__ne__ = lambda self, other: self.position != other.position
    member.top_role = top_role

    # Roles list (excluding @everyone for userinfo)
    member.roles = [mock_guild.default_role, top_role]

    # Avatar
    avatar = MagicMock()
    avatar.url = "https://example.com/avatar.png"
    member.avatar = avatar
    member.default_avatar = MagicMock()
    member.default_avatar.url = "https://example.com/default_avatar.png"

    # Timestamps
    member.created_at = datetime(2019, 6, 15, tzinfo=timezone.utc)
    member.joined_at = datetime(2020, 3, 1, tzinfo=timezone.utc)

    # Async methods
    member.kick = AsyncMock()
    member.ban = AsyncMock()
    member.timeout = AsyncMock()
    member.send = AsyncMock()
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()

    return member


# ---------------------------------------------------------------------------
# Target member (lower role, for moderation targets)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_target(mock_guild: MagicMock) -> MagicMock:
    """Return a mock ``discord.Member`` to be the target of mod actions."""
    target = MagicMock(spec=discord.Member)
    target.id = 500000000000000000
    target.name = "targetuser"
    target.display_name = "Target User"
    target.mention = "<@500000000000000000>"
    target.bot = False
    target.__str__ = lambda self: "targetuser"

    target.guild = mock_guild

    # Lower role than the bot so actions succeed
    top_role = MagicMock(spec=discord.Role)
    top_role.position = 2
    top_role.name = "Member"
    top_role.mention = "<@&role_member>"
    top_role.color = discord.Color.default()
    top_role.__gt__ = lambda self, other: self.position > other.position
    top_role.__lt__ = lambda self, other: self.position < other.position
    top_role.__eq__ = lambda self, other: self.position == other.position
    top_role.__ne__ = lambda self, other: self.position != other.position
    target.top_role = top_role

    target.roles = [mock_guild.default_role, top_role]

    # Avatar
    avatar = MagicMock()
    avatar.url = "https://example.com/target_avatar.png"
    target.avatar = avatar
    target.default_avatar = MagicMock()
    target.default_avatar.url = "https://example.com/default_avatar.png"

    target.created_at = datetime(2021, 1, 10, tzinfo=timezone.utc)
    target.joined_at = datetime(2021, 5, 20, tzinfo=timezone.utc)

    # Async methods
    target.kick = AsyncMock()
    target.ban = AsyncMock()
    target.timeout = AsyncMock()
    target.send = AsyncMock()
    target.add_roles = AsyncMock()
    target.remove_roles = AsyncMock()

    return target


# ---------------------------------------------------------------------------
# Text channel fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_text_channel(mock_guild: MagicMock) -> MagicMock:
    """Return a mock ``discord.TextChannel``."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 300000000000000000
    channel.name = "test-channel"
    channel.mention = "<#300000000000000000>"
    channel.guild = mock_guild
    channel.send = AsyncMock()
    channel.purge = AsyncMock(return_value=[MagicMock()] * 5)
    channel.delete = AsyncMock()
    return channel


# ---------------------------------------------------------------------------
# Interaction fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_interaction(
    mock_guild: MagicMock,
    mock_member: MagicMock,
    mock_text_channel: MagicMock,
) -> MagicMock:
    """Return a mock ``discord.Interaction`` wired to guild/member/channel."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = mock_guild
    interaction.guild_id = mock_guild.id
    interaction.user = mock_member
    interaction.channel = mock_text_channel
    interaction.channel_id = mock_text_channel.id

    # response object
    response = MagicMock()
    response.send_message = AsyncMock()
    response.defer = AsyncMock()
    response.is_done = MagicMock(return_value=False)
    interaction.response = response

    # followup object
    followup = MagicMock()
    followup.send = AsyncMock()
    interaction.followup = followup

    # original_response for poll reactions
    original_msg = AsyncMock()
    original_msg.add_reaction = AsyncMock()
    interaction.original_response = AsyncMock(return_value=original_msg)

    return interaction


# ---------------------------------------------------------------------------
# In-memory database fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def setup_database(tmp_path: Path) -> None:
    """Set up an in-memory SQLite database for tests.

    Monkeypatches ``config.DATABASE_PATH`` to use ``:memory:`` so tests
    never touch the real on-disk database.
    """
    db_path = str(tmp_path / "test_bot.db")
    with patch.object(config, "DATABASE_PATH", db_path):
        await init_db()
        yield  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Config file fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_config_file(tmp_path: Path) -> Path:
    """Create a temporary config.json and patch ``config.CONFIG_PATH``."""
    data: dict[str, Any] = {
        "welcome_channel": "welcome",
        "mod_log_channel": "mod-log",
        "ticket_category": "Support Tickets",
        "auto_role": "Member",
        "word_filter": ["badword1", "badword2"],
        "spam_threshold": 5,
        "spam_interval": 10,
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return config_file
