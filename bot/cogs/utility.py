"""Utility cog -- server info, user info, and polls.

Provides general-purpose slash commands available to all members.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.embeds import error_embed, info_embed

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Poll reaction emojis
# ---------------------------------------------------------------------------

_NUMBER_EMOJIS: list[str] = [
    "1\N{COMBINING ENCLOSING KEYCAP}",
    "2\N{COMBINING ENCLOSING KEYCAP}",
    "3\N{COMBINING ENCLOSING KEYCAP}",
    "4\N{COMBINING ENCLOSING KEYCAP}",
    "5\N{COMBINING ENCLOSING KEYCAP}",
    "6\N{COMBINING ENCLOSING KEYCAP}",
    "7\N{COMBINING ENCLOSING KEYCAP}",
    "8\N{COMBINING ENCLOSING KEYCAP}",
    "9\N{COMBINING ENCLOSING KEYCAP}",
]


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class Utility(commands.Cog):
    """General-purpose utility slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ==================================================================
    # Slash commands
    # ==================================================================

    # --- /serverinfo --------------------------------------------------

    @app_commands.command(
        name="serverinfo",
        description="Display information about the current server",
    )
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        guild = interaction.guild

        embed = info_embed(title=guild.name)

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="Owner",
            value=guild.owner.mention if guild.owner else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Created",
            value=f"<t:{int(guild.created_at.timestamp())}:R>",
            inline=True,
        )
        embed.add_field(
            name="Members",
            value=str(guild.member_count),
            inline=True,
        )

        # Online count -- requires the members to be cached (presences intent)
        online_count = sum(
            1
            for m in guild.members
            if m.status != discord.Status.offline and not m.bot
        )
        embed.add_field(name="Online", value=str(online_count), inline=True)

        bot_count = sum(1 for m in guild.members if m.bot)
        embed.add_field(name="Bots", value=str(bot_count), inline=True)

        embed.add_field(
            name="Text Channels",
            value=str(len(guild.text_channels)),
            inline=True,
        )
        embed.add_field(
            name="Voice Channels",
            value=str(len(guild.voice_channels)),
            inline=True,
        )
        embed.add_field(
            name="Boost Level",
            value=str(guild.premium_tier),
            inline=True,
        )
        embed.add_field(
            name="Boosts",
            value=str(guild.premium_subscription_count or 0),
            inline=True,
        )
        embed.add_field(
            name="Roles",
            value=str(len(guild.roles)),
            inline=True,
        )

        embed.set_footer(text=f"Guild ID: {guild.id}")

        await interaction.response.send_message(embed=embed)

    # --- /userinfo ----------------------------------------------------

    @app_commands.command(
        name="userinfo",
        description="Display information about a user",
    )
    @app_commands.describe(user="The member to look up (defaults to yourself)")
    async def userinfo(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        assert interaction.guild is not None

        member = user or interaction.user
        assert isinstance(member, discord.Member)

        # Use the member's top role colour, falling back to the default embed colour
        color = (
            member.top_role.color
            if member.top_role.color != discord.Color.default()
            else discord.Color.blue()
        )

        embed = info_embed(title=member.display_name)
        embed.color = color

        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        elif member.default_avatar:
            embed.set_thumbnail(url=member.default_avatar.url)

        embed.add_field(name="Username", value=member.name, inline=True)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(
            name="Account Created",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True,
        )

        if member.joined_at:
            joined_value = f"<t:{int(member.joined_at.timestamp())}:R>"
        else:
            joined_value = "Unknown"
        embed.add_field(name="Joined Server", value=joined_value, inline=True)

        embed.add_field(
            name="Top Role",
            value=member.top_role.mention,
            inline=True,
        )

        # List roles excluding @everyone
        roles = [r.mention for r in member.roles if r != interaction.guild.default_role]
        embed.add_field(
            name="Roles",
            value=" ".join(roles) if roles else "None",
            inline=False,
        )

        embed.add_field(
            name="Bot",
            value="Yes" if member.bot else "No",
            inline=True,
        )

        await interaction.response.send_message(embed=embed)

    # --- /poll --------------------------------------------------------

    @app_commands.command(
        name="poll",
        description="Create a poll with up to 9 options",
    )
    @app_commands.describe(
        question="The poll question",
        option1="Option 1",
        option2="Option 2",
        option3="Option 3",
        option4="Option 4",
        option5="Option 5",
        option6="Option 6",
        option7="Option 7",
        option8="Option 8",
        option9="Option 9",
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str | None = None,
        option4: str | None = None,
        option5: str | None = None,
        option6: str | None = None,
        option7: str | None = None,
        option8: str | None = None,
        option9: str | None = None,
    ) -> None:
        assert isinstance(interaction.user, (discord.Member, discord.User))

        # Collect all non-None options
        all_options = [
            option1, option2, option3, option4, option5,
            option6, option7, option8, option9,
        ]
        options: list[str] = [o for o in all_options if o is not None]

        if len(options) < 2:
            await interaction.response.send_message(
                embed=error_embed(
                    "Not Enough Options",
                    "You must provide at least **2** options for a poll.",
                ),
                ephemeral=True,
            )
            return

        # Build the description with numbered emoji lines
        description_lines: list[str] = []
        for idx, option in enumerate(options):
            description_lines.append(f"{_NUMBER_EMOJIS[idx]} {option}")

        embed = info_embed(
            title=f"\U0001f4ca {question}",
            description="\n\n".join(description_lines),
        )
        embed.set_footer(text=f"Poll by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)

        # Fetch the sent message so we can add reactions
        message = await interaction.original_response()
        for idx in range(len(options)):
            await message.add_reaction(_NUMBER_EMOJIS[idx])

    # ==================================================================
    # Error handler
    # ==================================================================

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle errors raised by slash commands in this cog."""

        log.exception("Unhandled error in utility cog", exc_info=error)
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
    await bot.add_cog(Utility(bot))
