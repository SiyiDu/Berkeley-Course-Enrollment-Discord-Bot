"""Slash command registration for the Berkeley bot."""

from __future__ import annotations

import logging
from typing import List

import discord
from discord import Embed, TextChannel, app_commands
from discord.ext import commands

from . import courses, state
from .config import BotConfig
from .enrollment import EnrollmentService
from .permissions import require_student
from .registration import RegistrationService
from .storage import DataStore
from .views import EnrollPanelView, DropMultiSelectView, VerifyPanelView


def register_commands(
    bot: commands.Bot,
    config: BotConfig,
    store: DataStore,
    registration: RegistrationService,
    enrollment: EnrollmentService,
) -> None:
    guild_object = discord.Object(id=config.guild_id)

    @bot.event
    async def on_ready() -> None:
        await bot.tree.sync(guild=guild_object)
        logging.info(
            "✅ Logged in as %s | Synced for %s | term=%s",
            bot.user,
            config.guild_id,
            state.current_term(),
        )

    @bot.event
    async def on_member_join(member: discord.Member) -> None:
        try:
            await member.send(
                "👋 Welcome!\n"
                "Please register to access the server:\n"
                "`/register student_id:<10 digits> email:<your@berkeley.edu> name:<Full Name>`\n\n"
                "Tip: You can run this here in DM; I will grant you the student role in the server."
            )
        except discord.Forbidden:
            pass

    @bot.tree.command(name="ping", description="Health check", guild=guild_object)
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Pong!", ephemeral=True)

    @bot.tree.command(
        name="panel",
        description="Post the enroll/drop panel in this channel",
        guild=guild_object,
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel(interaction: discord.Interaction) -> None:
        if interaction.channel is None or getattr(interaction.channel, "name", None) != "enroll":
            await interaction.response.send_message("Please run this in #enroll.", ephemeral=True)
            return
        view = EnrollPanelView(bot, registration, enrollment, store)
        await interaction.response.send_message(view=view)
        try:
            message = await interaction.original_response()
            await message.pin()
        except discord.HTTPException:
            pass

    @bot.tree.command(
        name="panel_to",
        description="Post the enroll/drop panel to a target channel",
        guild=guild_object,
    )
    @app_commands.describe(target="Channel to post the panel (e.g., #enroll)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel_to(interaction: discord.Interaction, target: TextChannel) -> None:
        view = EnrollPanelView(bot, registration, enrollment, store)
        embed = Embed(
            title="Course Enrollment Panel",
            description=(
                "Use the controls below to enroll in or drop course spaces.\n"
                "Pick a department range, then select a department, then enter course numbers."
            ),
        )
        try:
            message = await target.send(embed=embed, view=view)
            try:
                await message.pin()
            except discord.HTTPException:
                pass
            await interaction.response.send_message(f"✅ Posted panel to {target.mention}.", ephemeral=True)
        except discord.HTTPException as exc:
            await interaction.response.send_message(f"❌ Failed to post panel: {exc}", ephemeral=True)

    @bot.tree.command(
        name="verify_panel",
        description="Post the registration panel in this channel (#verify)",
        guild=guild_object,
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verify_panel(interaction: discord.Interaction) -> None:
        if interaction.channel is None or getattr(interaction.channel, "name", None) != "verify":
            await interaction.response.send_message("Please run this in #verify.", ephemeral=True)
            return
        view = VerifyPanelView(bot, registration)
        await interaction.response.send_message("Click the button below to start registration:", view=view)
        try:
            message = await interaction.original_response()
            await message.pin()
        except discord.HTTPException:
            pass

    @bot.tree.command(
        name="verify_panel_to",
        description="Post the registration panel to a target channel",
        guild=guild_object,
    )
    @app_commands.describe(target="Channel to post the verify panel (e.g., #verify)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verify_panel_to(interaction: discord.Interaction, target: TextChannel) -> None:
        view = VerifyPanelView(bot, registration)
        embed = Embed(
            title="Berkeley Student Registration",
            description=(
                "Click the button below to verify your student identity.\n"
                "You’ll be asked for your 10-digit SID, your @berkeley.edu email, and your full name."
            ),
        )
        try:
            message = await target.send(embed=embed, view=view)
            try:
                await message.pin()
            except discord.HTTPException:
                pass
            await interaction.response.send_message(f"✅ Posted verify panel to {target.mention}.", ephemeral=True)
        except discord.HTTPException as exc:
            await interaction.response.send_message(f"❌ Failed to post verify panel: {exc}", ephemeral=True)

    @bot.tree.command(
        name="register",
        description="Register (10-digit SID + berkeley.edu + name)",
    )
    @app_commands.describe(
        student_id="10-digit Student ID",
        email="your@berkeley.edu",
        name="Your full name (1-50 chars)",
    )
    async def register_cmd(interaction: discord.Interaction, student_id: str, email: str, name: str) -> None:
        ok, message = await registration.register_user(bot, interaction, student_id, email, name)
        prefix = "✅ " if ok else "❌ "
        await interaction.response.send_message(prefix + message, ephemeral=True)

    @bot.tree.command(name="whoami", description="Show my registration")
    async def whoami(interaction: discord.Interaction) -> None:
        record = registration.user_get(interaction.user.id)
        if not record:
            await interaction.response.send_message("You are not registered. Use `/register`.", ephemeral=True)
            return
        sid = record["student_id"]
        email = record["email"]
        name = record["name"]
        masked_sid = f"{sid[:2]}******{sid[-2:]}"
        role_line = ""
        target_guild = None
        if interaction.guild and interaction.guild.id == config.guild_id:
            target_guild = interaction.guild
        else:
            target_guild = bot.get_guild(config.guild_id)
        if target_guild:
            try:
                member = target_guild.get_member(interaction.user.id) or await target_guild.fetch_member(
                    interaction.user.id
                )
            except discord.HTTPException:
                member = None
            if member:
                has_role = registration.member_has_student(member)
                role_line = f"\n- Role: {'✅ has ' if has_role else '❌ no '}{registration.student_role_name}"
        await interaction.response.send_message(
            f"You're registered:\n- SID: `{masked_sid}`\n- Email: `{email}`\n- Name: `{name}`{role_line}",
            ephemeral=True,
        )

    @bot.tree.command(name="unregister", description="Remove my registration")
    async def unregister_cmd(interaction: discord.Interaction) -> None:
        registration.user_delete(interaction.user.id)
        target_guild = None
        if interaction.guild and interaction.guild.id == config.guild_id:
            target_guild = interaction.guild
        else:
            target_guild = bot.get_guild(config.guild_id)
        if target_guild:
            await registration.remove_student_role(target_guild, interaction.user.id)
        await interaction.response.send_message("✅ Registration removed.", ephemeral=True)

    @bot.tree.command(
        name="enroll",
        description="Join or create a private course thread",
        guild=guild_object,
    )
    @app_commands.describe(dept="Department (e.g. PHYSICS, CS)", number="Course number (e.g. 105)")
    @app_commands.autocomplete(dept=courses.dept_autocomplete)
    @require_student(registration)
    async def enroll_cmd(interaction: discord.Interaction, dept: str, number: str) -> None:
        if interaction.channel and getattr(interaction.channel, "name", None) != "enroll":
            await interaction.response.send_message("⚠️ Please use this command in the #enroll channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        dept_up = dept.upper()
        if dept_up not in courses.VALID_DEPTS:
            examples = ", ".join(sorted(courses.VALID_DEPTS[:10]))
            await interaction.followup.send(
                f"⚠️ Unknown department `{dept_up}`. Example: {examples} ...",
                ephemeral=True,
            )
            return
        ok, msg = await enrollment.enroll_one(interaction.guild, interaction.user, dept_up, number)
        prefix = "✅ " if ok else "❌ "
        await interaction.followup.send(prefix + msg, ephemeral=True)

    @bot.tree.command(
        name="drop",
        description="Leave a course (select from your current enrollments)",
        guild=guild_object,
    )
    @require_student(registration)
    async def drop_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        slugs = store.list_enrollments_for_term(interaction.user.id, state.current_term())
        if not slugs:
            await interaction.followup.send("You haven’t joined any courses this term.", ephemeral=True)
            return
        await interaction.followup.send(
            "Select a course to leave (single-select). For multi-drop, use the Drop courses button on the panel.",
            view=DropMultiSelectView(interaction.user, registration, enrollment, slugs[:25]),
            ephemeral=True,
        )

    @bot.tree.command(
        name="drop_exact",
        description="Leave a specific course by dept & number",
        guild=guild_object,
    )
    @app_commands.describe(dept="e.g. PHYSICS", number="e.g. 105")
    @app_commands.autocomplete(dept=courses.dept_autocomplete)
    @require_student(registration)
    async def drop_exact(interaction: discord.Interaction, dept: str, number: str) -> None:
        await interaction.response.defer(ephemeral=True)
        slug = courses.course_slug_for(dept.upper(), number)
        ok, fail = await enrollment.drop_many(interaction.guild, interaction.user, [slug])
        if ok:
            await interaction.followup.send(f"✅ You’ve left **{ok[0]}**.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {fail[0]}", ephemeral=True)

    @bot.tree.command(
        name="mycourses",
        description="List your enrolled courses",
        guild=guild_object,
    )
    @require_student(registration)
    async def mycourses(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        slugs = store.list_enrollments_for_term(interaction.user.id, state.current_term())
        if not slugs:
            await interaction.followup.send(
                f"You haven’t joined any courses this term ({state.current_term().upper()}).",
                ephemeral=True,
            )
            return
        lines: List[str] = []
        for slug in slugs:
            meta = store.index_get(slug)
            if meta:
                lines.append(f"- <#{meta['thread_id']}> (`#{slug}`)")
            else:
                lines.append(f"- `#{slug}` (not indexed)")
        await interaction.followup.send(
            "Here are your current courses:\n" + "\n".join(lines),
            ephemeral=True,
        )

    @bot.tree.command(
        name="archive",
        description="Archive and lock all current-term course threads",
        guild=guild_object,
    )
    @app_commands.checks.has_permissions(manage_threads=True)
    async def archive(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command must be used in the server.", ephemeral=True)
            return
        category = discord.utils.get(guild.categories, name=courses.course_category_name())
        if not category:
            await interaction.followup.send("No course category found.", ephemeral=True)
            return

        count = 0
        current_term = state.current_term()
        for channel in category.channels:
            if not isinstance(channel, discord.TextChannel):
                continue
            for thread in list(channel.threads):
                if thread.name.startswith(current_term + "-"):
                    try:
                        await thread.edit(locked=True, archived=True)
                        count += 1
                    except discord.HTTPException:
                        pass
            for private in (False, True):
                try:
                    async for thread in channel.archived_threads(limit=None, private=private):
                        if thread.name.startswith(current_term + "-"):
                            try:
                                await thread.edit(locked=True, archived=True)
                                count += 1
                            except discord.HTTPException:
                                pass
                except discord.HTTPException:
                    continue

        await interaction.followup.send(f"✅ Archived and locked {count} course threads.", ephemeral=True)

    @bot.tree.command(
        name="set_term",
        description="Set the current academic term",
        guild=guild_object,
    )
    @app_commands.describe(term="e.g. fa25 or sp26")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_term(interaction: discord.Interaction, term: str) -> None:
        try:
            state.set_current_term(term)
        except ValueError:
            await interaction.response.send_message("Format error: must be faYY or spYY (e.g., fa25).", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ Term set to **{state.current_term().upper()}**.",
            ephemeral=True,
        )

    @bot.tree.command(
        name="sync",
        description="Re-sync slash commands for this guild",
        guild=guild_object,
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await bot.tree.sync(guild=guild_object)
        await interaction.followup.send("✅ Commands re-synced.", ephemeral=True)

