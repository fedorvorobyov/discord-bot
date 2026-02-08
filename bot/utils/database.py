"""Async SQLite database utilities for the Discord bot.

Uses ``aiosqlite`` for non-blocking database access.  Every public helper
opens **and closes** its own connection so callers never need to worry about
connection lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from bot import config

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


async def get_db() -> aiosqlite.Connection:
    """Return a new :class:`aiosqlite.Connection` to the bot database.

    The caller is responsible for closing the connection (ideally via
    ``async with``).
    """
    conn = await aiosqlite.connect(config.DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    return conn


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create the database file, parent directories, and all tables.

    This **must** be called once during bot startup before any other database
    function is used.
    """
    # Ensure the data/ directory exists
    db_path = Path(config.DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # Enable Write-Ahead Logging for better concurrent read performance
        await db.execute("PRAGMA journal_mode=WAL;")

        # -- Moderation warnings -----------------------------------------------
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id      INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                moderator_id  INTEGER NOT NULL,
                reason        TEXT    NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # -- Support tickets ---------------------------------------------------
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL UNIQUE,
                status      TEXT    NOT NULL DEFAULT 'open',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # -- Reaction-role menus -----------------------------------------------
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS role_menus (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                message_id  INTEGER NOT NULL,
                emoji       TEXT    NOT NULL,
                role_id     INTEGER NOT NULL
            );
            """
        )

        await db.commit()


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


async def add_warning(
    guild_id: int,
    user_id: int,
    moderator_id: int,
    reason: str,
) -> int:
    """Insert a new warning and return its row id."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason),
        )
        await db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


async def get_warnings(guild_id: int, user_id: int) -> list[dict[str, Any]]:
    """Return all warnings for a user in a guild as a list of dicts."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, guild_id, user_id, moderator_id, reason, created_at
            FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (guild_id, user_id),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_warning_count(guild_id: int, user_id: int) -> int:
    """Return the total number of warnings for a user in a guild."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        assert row is not None
        return int(row[0])


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


async def create_ticket(
    guild_id: int,
    user_id: int,
    channel_id: int,
) -> int:
    """Create a new support ticket and return its row id."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO tickets (guild_id, user_id, channel_id)
            VALUES (?, ?, ?)
            """,
            (guild_id, user_id, channel_id),
        )
        await db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


async def close_ticket(channel_id: int) -> None:
    """Mark the ticket associated with *channel_id* as closed."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE tickets SET status = 'closed' WHERE channel_id = ?",
            (channel_id,),
        )
        await db.commit()


async def get_open_ticket(
    guild_id: int,
    user_id: int,
) -> dict[str, Any] | None:
    """Return the open ticket for a user in a guild, or ``None``."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, guild_id, user_id, channel_id, status, created_at
            FROM tickets
            WHERE guild_id = ? AND user_id = ? AND status = 'open'
            LIMIT 1
            """,
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Role menus
# ---------------------------------------------------------------------------


async def add_role_menu(
    guild_id: int,
    channel_id: int,
    message_id: int,
    emoji: str,
    role_id: int,
) -> None:
    """Add a reaction-role mapping for a message."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO role_menus (guild_id, channel_id, message_id, emoji, role_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, message_id, emoji, role_id),
        )
        await db.commit()


async def get_role_menus(guild_id: int) -> list[dict[str, Any]]:
    """Return all role-menu entries for a guild."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, guild_id, channel_id, message_id, emoji, role_id
            FROM role_menus
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_role_menu_by_message(message_id: int) -> list[dict[str, Any]]:
    """Return all emoji-role mappings for a specific message.

    Each dict contains ``emoji`` and ``role_id`` keys.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT emoji, role_id FROM role_menus WHERE message_id = ?",
            (message_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_role_menu(message_id: int) -> None:
    """Delete all role-menu entries associated with *message_id*."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM role_menus WHERE message_id = ?",
            (message_id,),
        )
        await db.commit()
