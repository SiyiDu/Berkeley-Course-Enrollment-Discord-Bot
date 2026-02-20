"""Slash command registration for the Berkeley bot."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import List

import discord
from discord import Embed, TextChannel, app_commands
from discord.ext import commands

from . import courses, state
from .config import BotConfig
from .enrollment import EnrollmentService
from .knowledge_client import KnowledgeClient
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
    knowledge_client = KnowledgeClient(config.engine_base_url, config.client_id, config.client_token)

    course_re = re.compile(r"^[A-Za-z]{2,10}\s*\d{1,3}[A-Za-z]?$")
    term_re = re.compile(r"\b\d{4}-(spring|summer|fall|winter)\b", re.IGNORECASE)
    short_term_re = re.compile(r"\b(fa|sp|su|wi)\d{2}\b", re.IGNORECASE)

    def _parse_scope_input(raw: str) -> tuple[dict[str, str], str]:
        if "|" not in raw:
            return {}, raw.strip()
        left, right = raw.split("|", 1)
        target = left.strip().strip('"')
        question = right.strip()
        term = None
        section = None
        term_match = term_re.search(target)
        if term_match:
            term = term_match.group(0)
            target = term_re.sub("", target).strip()
        tokens = target.split()
        if term and tokens:
            if tokens[-1].isdigit():
                section = tokens[-1]
                tokens = tokens[:-1]
        target = " ".join(tokens) if tokens else target

        scope: dict[str, str] = {"type": "auto"}
        if course_re.match(target.replace(" ", "")):
            scope["type"] = "course"
            scope["course_code"] = target.replace(" ", "").upper()
            if term:
                scope["term"] = term
            if section:
                scope["section"] = section
        elif target:
            scope["type"] = "professor"
            scope["professor_name"] = target
            if term:
                scope["term"] = term
        return scope, question

    def _parse_course_context(name: str) -> dict[str, str]:
        tokens = re.split(r"[-_\s]+", name.lower())
        term = None
        course_code = None
        dept_token = None
        number_token = None

        for token in tokens:
            if not term and short_term_re.fullmatch(token):
                term = token
                continue
            if not term:
                long_match = term_re.search(token)
                if long_match:
                    term = long_match.group(0).lower()
            if not course_code:
                course_match = re.fullmatch(r"([a-z]{2,10})(\d{1,3}[a-z]?)", token)
                if course_match:
                    course_code = (course_match.group(1) + course_match.group(2)).upper()
            if not dept_token and token.isalpha() and len(token) >= 2:
                dept_token = token
            if not number_token and re.fullmatch(r"\d{1,3}[a-z]?", token):
                number_token = token

        if not course_code and dept_token and number_token:
            course_code = f"{dept_token}{number_token}".upper()

        result: dict[str, str] = {}
        if course_code:
            result["course_code"] = course_code
        if term:
            result["term"] = term
        return result

    def _derive_catalog_fields(message: discord.Message) -> dict[str, str]:
        if not config.course_category_id:
            return {}
        channel = message.channel
        parent = None
        if isinstance(channel, discord.Thread):
            parent = channel.parent
        else:
            parent = channel
        category_id = getattr(parent, "category_id", None)
        if category_id != config.course_category_id:
            return {}

        candidates = []
        if isinstance(channel, discord.Thread):
            candidates.append(channel.name)
        if parent and getattr(parent, "name", None):
            candidates.append(parent.name)
        if parent and parent.category and parent.category.name:
            candidates.append(parent.category.name)

        catalog: dict[str, str] = {}
        for name in candidates:
            parsed = _parse_course_context(name)
            if parsed.get("course_code") and not catalog.get("course_code"):
                catalog["course_code"] = parsed["course_code"]
            if parsed.get("term") and not catalog.get("term"):
                catalog["term"] = parsed["term"]
        if config.default_professor_name and not catalog.get("professor_name"):
            catalog["professor_name"] = config.default_professor_name
        return catalog

    async def _ingest_message(message: discord.Message) -> None:
        if not message.guild:
            return
        catalog = _derive_catalog_fields(message)
        payload = {
            "platform": "discord",
            "workspace_id": str(message.guild.id),
            "channel_id": str(message.channel.id),
            "message_id": str(message.id),
            "author_id": str(message.author.id),
            "content": message.content,
            "timestamp": message.created_at.isoformat(),
            "permalink": message.jump_url,
            "author_name": message.author.display_name,
            "reply_to_message_id": str(message.reference.message_id)
            if message.reference and message.reference.message_id
            else None,
            "attachments": [attachment.url for attachment in message.attachments],
            "message_url": message.jump_url,
            "course_code": catalog.get("course_code"),
            "term": catalog.get("term"),
            "professor_name": catalog.get("professor_name"),
        }
        try:
            await knowledge_client.ingest_message(payload)
        except Exception as exc:
            logging.warning("Ingest failed: %s", exc)

    async def _ask_backend(
        query: str,
        workspace_id: str | None,
        channel_id: str | None,
        user_id: str | None,
        scope: dict[str, str] | None = None,
        mode: str = "auto",
        viewer_role: str = "student",
    ) -> dict:
        try:
            return await knowledge_client.ask(
                query=query,
                viewer_role=viewer_role,
                source="discord",
                workspace_id=workspace_id,
                channel_id=channel_id,
                discord_user_id=user_id,
                scope=scope,
                mode=mode,
            )
        except Exception as exc:
            logging.warning("Ask failed: %s", exc)
            return {"answer": "The knowledge engine is unavailable right now."}

    def _strip_mention(content: str) -> str:
        if not bot.user:
            return content.strip()
        content = content.replace(f"<@{bot.user.id}>", "")
        content = content.replace(f"<@!{bot.user.id}>", "")
        return content.strip()

    def _format_response(payload: dict) -> str:
        answer = payload.get("answer") or "No answer returned."
        lines = [f"**Answer:** {answer}"]
        cards = payload.get("cards", [])
        if cards:
            sources = "\n".join(
                f"- {card.get('title', 'Untitled')} (`{card.get('id', '')[:6]}`)"
                for card in cards[:3]
            )
            lines.append("**Sources:**\n" + sources)
        evidence = payload.get("evidence", [])
        if evidence:
            snippets = "\n".join(f"- {item.get('excerpt', '')}" for item in evidence[:2])
            lines.append("**Evidence:**\n" + snippets)
        if payload.get("resolved", {}).get("mode") == "experience":
            strength = payload.get("experience_strength", {})
            lines.append(
                "**Signals:** "
                f"{strength.get('signal_count', 0)} mentions | "
                f"{strength.get('unique_authors', 0)} authors | "
                f"{strength.get('time_range_days', 0)} days"
            )
        candidates = payload.get("disambiguation", {}).get("candidates") or payload.get("resolved", {}).get(
            "disambiguation", {}
        ).get("candidates", [])
        if candidates:
            hint = ", ".join(candidate.get("display", "") for candidate in candidates[:3])
            lines.append(f"**Did you mean:** {hint}")
        return "\n".join(lines)

    class DisambiguationView(discord.ui.View):
        def __init__(
            self,
            candidates: list[dict],
            query: str,
            workspace_id: str | None,
            channel_id: str | None,
            user_id: str | None,
        ) -> None:
            super().__init__(timeout=60)
            self.query = query
            self.workspace_id = workspace_id
            self.channel_id = channel_id
            self.user_id = user_id
            options = []
            for candidate in candidates[:25]:
                scope_type = candidate.get("type")
                value_id = candidate.get("offering_id") or candidate.get("professor_id")
                if not scope_type or not value_id:
                    continue
                label = candidate.get("display", "Candidate")
                options.append(
                    discord.SelectOption(label=label[:100], value=f"{scope_type}:{value_id}")
                )
            self.add_item(DisambiguationSelect(options, self))

    class DisambiguationSelect(discord.ui.Select):
        def __init__(self, options: list[discord.SelectOption], view: DisambiguationView) -> None:
            super().__init__(placeholder="Select a scope", options=options)
            self.view_ref = view

        async def callback(self, interaction: discord.Interaction) -> None:
            value = self.values[0]
            scope_type, scope_id = value.split(":", 1)
            scope: dict[str, str] = {"type": scope_type}
            if scope_type == "course":
                scope["offering_id"] = scope_id
            else:
                scope["professor_id"] = scope_id
            reply = await _ask_backend(
                query=self.view_ref.query,
                workspace_id=self.view_ref.workspace_id,
                channel_id=self.view_ref.channel_id,
                user_id=self.view_ref.user_id,
                scope=scope,
            )
            await interaction.response.send_message(_format_response(reply), ephemeral=True)

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

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        asyncio.create_task(_ingest_message(message))
        if bot.user and bot.user in message.mentions:
            content = _strip_mention(message.content)
            if content:
                scope, question = _parse_scope_input(content)
                payload = await _ask_backend(
                    query=question,
                    workspace_id=str(message.guild.id),
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    scope=scope,
                )
                if payload.get("disambiguation", {}).get("needed"):
                    view = DisambiguationView(
                        payload.get("disambiguation", {}).get("candidates", []),
                        question,
                        str(message.guild.id),
                        str(message.channel.id),
                        str(message.author.id),
                    )
                    try:
                        await message.reply("Select the correct scope:", view=view, mention_author=False)
                    except discord.HTTPException:
                        pass
                else:
                    reply = _format_response(payload)
                    try:
                        await message.reply(reply, mention_author=False)
                    except discord.HTTPException:
                        pass
        await bot.process_commands(message)

    @bot.tree.command(name="ask", description="Ask the knowledge engine", guild=guild_object)
    @app_commands.describe(target="Course code or professor", term="Term (e.g., 2026-spring)", section="Section")
    @app_commands.describe(question="Your question")
    async def ask_cmd(
        interaction: discord.Interaction,
        question: str,
        target: str | None = None,
        term: str | None = None,
        section: str | None = None,
    ) -> None:
        await interaction.response.defer()
        scope: dict[str, str] = {}
        if target:
            scope, question = _parse_scope_input(f"{target} {term or ''} {section or ''} | {question}")
        payload = await _ask_backend(
            query=question,
            workspace_id=str(interaction.guild_id) if interaction.guild_id else None,
            channel_id=str(interaction.channel.id) if interaction.channel else None,
            user_id=str(interaction.user.id),
            scope=scope,
        )
        if payload.get("disambiguation", {}).get("needed"):
            view = DisambiguationView(
                payload.get("disambiguation", {}).get("candidates", []),
                question,
                str(interaction.guild_id) if interaction.guild_id else None,
                str(interaction.channel.id) if interaction.channel else None,
                str(interaction.user.id),
            )
            await interaction.followup.send("Select the correct scope:", view=view, ephemeral=True)
        else:
            await interaction.followup.send(_format_response(payload))

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
