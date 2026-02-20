"""Discord UI components for enrollment and registration."""

from __future__ import annotations

import re
from typing import List

import discord
from discord import ui
from discord.ext import commands

from . import courses, state
from .enrollment import EnrollmentService
from .registration import RegistrationService
from .storage import DataStore


BUCKETS = {
    "A–G": [d for d in courses.VALID_DEPTS if d[0] <= "G"],
    "H–N": [d for d in courses.VALID_DEPTS if "H" <= d[0] <= "N"],
    "O–Z": [d for d in courses.VALID_DEPTS if "O" <= d[0] <= "Z"],
}


class VerifyRegisterModal(ui.Modal):
    def __init__(self, bot: commands.Bot, registration: RegistrationService):
        super().__init__(title="Berkeley Student Registration")
        self._bot = bot
        self._registration = registration
        self.sid = ui.TextInput(
            label="Student ID (10 digits)",
            placeholder="e.g., 3030XXXXXX",
            max_length=10,
            required=True,
        )
        self.email = ui.TextInput(
            label="Berkeley Email",
            placeholder="yourname@berkeley.edu",
            max_length=80,
            required=True,
        )
        self.name = ui.TextInput(
            label="Full Name",
            placeholder="Your real name",
            max_length=50,
            required=True,
        )
        self.add_item(self.sid)
        self.add_item(self.email)
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ok, message = await self._registration.register_user(
            self._bot,
            interaction,
            str(self.sid.value),
            str(self.email.value),
            str(self.name.value),
        )
        prefix = "✅ " if ok else "❌ "
        await interaction.response.send_message(prefix + message, ephemeral=True)


class VerifyPanelView(ui.View):
    def __init__(self, bot: commands.Bot, registration: RegistrationService):
        super().__init__(timeout=None)
        self._bot = bot
        self._registration = registration

    @ui.button(label="Start Registration", style=discord.ButtonStyle.success)
    async def start_registration(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        await interaction.response.send_modal(VerifyRegisterModal(self._bot, self._registration))


class EnrollPanelView(ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        registration: RegistrationService,
        enrollment: EnrollmentService,
        store: DataStore,
    ):
        super().__init__(timeout=None)
        self._bot = bot
        self._registration = registration
        self._enrollment = enrollment
        self._store = store

    @ui.button(label="Enroll courses", style=discord.ButtonStyle.primary)
    async def enroll_courses(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use this command inside the server.", ephemeral=True)
            return
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(
            interaction.user.id
        )
        if not member or not self._registration.member_has_student(member):
            await interaction.response.send_message(
                f"🔒 You need **{self._registration.student_role_name}** role. Register with `/register ...`.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "Pick a department range first:",
            view=DeptBucketView(
                interaction.user,
                self._registration,
                self._enrollment,
                self._store,
            ),
            ephemeral=True,
        )

    @ui.button(label="Drop courses", style=discord.ButtonStyle.danger)
    async def drop_courses(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use this command inside the server.", ephemeral=True)
            return
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(
            interaction.user.id
        )
        if not member or not self._registration.member_has_student(member):
            await interaction.response.send_message(
                f"🔒 You need **{self._registration.student_role_name}** role. Register with `/register ...`.",
                ephemeral=True,
            )
            return
        slugs = self._store.list_enrollments_for_term(interaction.user.id, state.current_term())
        if not slugs:
            await interaction.response.send_message("You don’t have any courses this term.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select courses to drop (multi-select):",
            view=DropMultiSelectView(
                interaction.user,
                self._registration,
                self._enrollment,
                slugs[:25],
            ),
            ephemeral=True,
        )


class DeptBucketView(ui.View):
    def __init__(
        self,
        user: discord.User,
        registration: RegistrationService,
        enrollment: EnrollmentService,
        store: DataStore,
    ):
        super().__init__(timeout=120)
        self.add_item(DeptBucketSelect(user.id, registration, enrollment, store))


class DeptBucketSelect(ui.Select):
    def __init__(
        self,
        user_id: int,
        registration: RegistrationService,
        enrollment: EnrollmentService,
        store: DataStore,
    ):
        self._user_id = user_id
        self._registration = registration
        self._enrollment = enrollment
        self._store = store
        options = [discord.SelectOption(label=bucket, value=bucket) for bucket in BUCKETS.keys()]
        super().__init__(
            placeholder="Choose range (A–G / H–N / O–Z)",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This menu isn’t for you.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("Use this menu inside the server.", ephemeral=True)
            return
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(
            interaction.user.id
        )
        if not member or not self._registration.member_has_student(member):
            await interaction.response.send_message(
                f"🔒 You need **{self._registration.student_role_name}** role. Register with `/register ...`.",
                ephemeral=True,
            )
            return
        bucket = self.values[0]
        depts = BUCKETS[bucket]
        await interaction.response.edit_message(
            content=f"Pick a department in **{bucket}**:",
            view=DeptPickView(
                interaction.user,
                depts,
                self._registration,
                self._enrollment,
                self._store,
            ),
        )


class DeptPickView(ui.View):
    def __init__(
        self,
        user: discord.User,
        depts: List[str],
        registration: RegistrationService,
        enrollment: EnrollmentService,
        store: DataStore,
    ):
        super().__init__(timeout=180)
        self.add_item(DeptPickSelect(user.id, depts, registration, enrollment, store))


class DeptPickSelect(ui.Select):
    def __init__(
        self,
        user_id: int,
        depts: List[str],
        registration: RegistrationService,
        enrollment: EnrollmentService,
        store: DataStore,
    ):
        self._user_id = user_id
        self._registration = registration
        self._enrollment = enrollment
        self._store = store
        options = [discord.SelectOption(label=dept, value=dept) for dept in depts[:25]]
        super().__init__(placeholder="Select department", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This menu isn’t for you.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("Use this menu inside the server.", ephemeral=True)
            return
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(
            interaction.user.id
        )
        if not member or not self._registration.member_has_student(member):
            await interaction.response.send_message(
                f"🔒 You need **{self._registration.student_role_name}** role. Register with `/register ...`.",
                ephemeral=True,
            )
            return
        dept_up = self.values[0]
        await interaction.response.send_modal(
            EnrollNumbersModal(
                self._user_id,
                dept_up,
                self._registration,
                self._enrollment,
            )
        )


class EnrollNumbersModal(ui.Modal):
    def __init__(
        self,
        user_id: int,
        dept_up: str,
        registration: RegistrationService,
        enrollment: EnrollmentService,
    ):
        super().__init__(title="Enroll multiple courses")
        self._user_id = user_id
        self._dept_up = dept_up
        self._registration = registration
        self._enrollment = enrollment
        self.numbers = ui.TextInput(
            label="Course numbers (comma-separated)",
            placeholder="e.g., 7B, 105, 126",
            style=discord.TextStyle.short,
            max_length=200,
            required=True,
        )
        self.add_item(self.numbers)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This form isn’t for you.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("Use this form inside the server.", ephemeral=True)
            return
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(
            interaction.user.id
        )
        if not member or not self._registration.member_has_student(member):
            await interaction.response.send_message(
                f"🔒 You need **{self._registration.student_role_name}** role. Register with `/register ...`.",
                ephemeral=True,
            )
            return
        raw = str(self.numbers.value)
        parts = [p.strip() for p in re.split(r"[,\s]+", raw) if p.strip()]
        seen, numbers = set(), []
        for part in parts:
            normalized = part.upper()
            if normalized not in seen:
                seen.add(normalized)
                numbers.append(normalized)
            if len(numbers) >= 20:
                break
        if not numbers:
            await interaction.response.send_message("No valid numbers provided.", ephemeral=True)
            return

        results = []
        for number in numbers:
            ok, msg = await self._enrollment.enroll_one(interaction.guild, interaction.user, self._dept_up, number)
            results.append(("✅ " if ok else "❌ ") + msg)

        await interaction.response.send_message(
            f"**Department:** {self._dept_up}\n" + "\n".join(results),
            ephemeral=True,
        )


class DropMultiSelectView(ui.View):
    def __init__(
        self,
        user: discord.User,
        registration: RegistrationService,
        enrollment: EnrollmentService,
        slugs: List[str],
    ):
        super().__init__(timeout=180)
        self.add_item(DropMultiSelect(user.id, registration, enrollment, slugs))


class DropMultiSelect(ui.Select):
    def __init__(
        self,
        user_id: int,
        registration: RegistrationService,
        enrollment: EnrollmentService,
        slugs: List[str],
    ):
        self._user_id = user_id
        self._registration = registration
        self._enrollment = enrollment
        options = [discord.SelectOption(label=slug, value=slug) for slug in slugs[:25]]
        super().__init__(
            placeholder="Pick one or more courses to drop",
            min_values=1,
            max_values=min(25, len(options)),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This menu isn’t for you.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("Use this menu inside the server.", ephemeral=True)
            return
        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(
            interaction.user.id
        )
        if not member or not self._registration.member_has_student(member):
            await interaction.response.send_message(
                f"🔒 You need **{self._registration.student_role_name}** role. Register with `/register ...`.",
                ephemeral=True,
            )
            return
        chosen = list(self.values)
        ok, fail = await self._enrollment.drop_many(interaction.guild, interaction.user, chosen)
        responses = []
        if ok:
            responses.append("✅ Dropped:\n- " + "\n- ".join(ok))
        if fail:
            responses.append("❌ Failed:\n- " + "\n- ".join(fail))
        text = "\n".join(responses) if responses else "Nothing to drop."
        await interaction.response.send_message(text, ephemeral=True)
