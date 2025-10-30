"""Command checks and decorators."""

from __future__ import annotations

import discord

from discord import app_commands

from .registration import RegistrationService


def require_student(registration: RegistrationService):
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message(
                "Commands must be used in the server.",
                ephemeral=True,
            )
            return False
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(
            interaction.user.id
        )
        if not member or not registration.member_has_student(member):
            await interaction.response.send_message(
                "🔒 You need the student role. Register with `/register ...` (you can run it in DM).",
                ephemeral=True,
            )
            return False
        return True

    return app_commands.check(predicate)
