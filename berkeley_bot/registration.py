"""Student registration workflows and validations."""

from __future__ import annotations

import re
from typing import Optional, Tuple

import discord
from discord.ext import commands

from .config import BotConfig
from .storage import DataStore


SID_PATTERN = re.compile(r"^\d{10}$")


class RegistrationService:
    def __init__(self, store: DataStore, config: BotConfig):
        self._store = store
        self._config = config

    @property
    def student_role_name(self) -> str:
        return self._config.student_role_name

    # ------------ Validation ------------
    def validate_inputs(self, student_id: str, email: str, name: str) -> Optional[str]:
        if not SID_PATTERN.fullmatch(student_id):
            return "SID must be exactly 10 digits."
        if not email.lower().endswith(self._config.berkeley_suffix.lower()):
            return f"Email must end with {self._config.berkeley_suffix}."
        trimmed = name.strip()
        if not (1 <= len(trimmed) <= 50):
            return "Name length must be between 1 and 50 characters."
        return None

    # ------------ Persistence ------------
    def user_get(self, uid: int) -> Optional[dict]:
        return self._store.user_get(uid)

    def user_upsert(self, uid: int, student_id: str, email: str, name: str) -> None:
        self._store.user_upsert(uid, student_id, email.lower(), name.strip())

    def user_delete(self, uid: int) -> None:
        self._store.user_delete(uid)

    # ------------ Roles ------------
    async def ensure_student_role(self, guild: discord.Guild) -> discord.Role:
        role = discord.utils.get(guild.roles, name=self._config.student_role_name)
        if role:
            return role
        return await guild.create_role(
            name=self._config.student_role_name,
            mentionable=False,
            reason="bootstrap student role",
        )

    def member_has_student(self, member: discord.Member) -> bool:
        return any(r.name == self._config.student_role_name for r in member.roles)

    async def grant_student_role(self, guild: discord.Guild, user_id: int) -> bool:
        role = await self.ensure_student_role(guild)
        try:
            member = await guild.fetch_member(user_id)
        except (discord.NotFound, discord.HTTPException, discord.Forbidden):
            return False
        if self.member_has_student(member):
            return True
        try:
            await member.add_roles(role, reason="registration approved")
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def remove_student_role(self, guild: discord.Guild, user_id: int) -> None:
        role = discord.utils.get(guild.roles, name=self._config.student_role_name)
        if not role:
            return
        try:
            member = await guild.fetch_member(user_id)
        except (discord.NotFound, discord.HTTPException, discord.Forbidden):
            return
        if role not in member.roles:
            return
        try:
            await member.remove_roles(role, reason="unregister")
        except (discord.Forbidden, discord.HTTPException):
            return

    # ------------ Workflow ------------
    async def register_user(
        self,
        bot: commands.Bot,
        interaction: discord.Interaction,
        student_id: str,
        email: str,
        name: str,
    ) -> Tuple[bool, str]:
        error = self.validate_inputs(student_id, email, name)
        if error:
            return False, error

        self.user_upsert(interaction.user.id, student_id, email, name)

        target_guild: Optional[discord.Guild] = None
        if interaction.guild and interaction.guild.id == self._config.guild_id:
            target_guild = interaction.guild
        else:
            target_guild = bot.get_guild(self._config.guild_id)

        if target_guild:
            granted = await self.grant_student_role(target_guild, interaction.user.id)
            if granted:
                return True, f"Registered and granted **{self._config.student_role_name}** role."

        return False, "Registered, but I couldn’t grant the role automatically. Please try again in the server."
