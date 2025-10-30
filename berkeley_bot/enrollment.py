"""Course enrollment workflows."""

from __future__ import annotations

from typing import List, Tuple

import discord

from . import courses, state
from .channels import (
    ensure_category,
    ensure_container_text_channel,
    ensure_private_course_thread,
    fetch_archived_thread_by_name,
)
from .storage import DataStore


class EnrollmentService:
    def __init__(self, store: DataStore, *, private_containers: bool):
        self._store = store
        self._private_containers = private_containers

    async def enroll_one(
        self,
        guild: discord.Guild,
        user: discord.abc.User,
        dept_up: str,
        number: str,
    ) -> Tuple[bool, str]:
        term = state.current_term()
        slug = courses.course_slug_for(dept_up, number, term=term)
        category = await ensure_category(guild, courses.course_category_name(term))
        container_name = courses.container_name_for(dept_up, term=term)
        container = await ensure_container_text_channel(guild, category, container_name)
        thread = await ensure_private_course_thread(container, slug)

        if self._private_containers:
            try:
                await container.set_permissions(user, view_channel=True, read_message_history=True)
            except (discord.Forbidden, discord.HTTPException):
                pass

        if user in getattr(thread, "members", []):
            return True, f"Already in <#{thread.id}> (**{slug}**)."

        try:
            await thread.add_user(user)
        except (discord.Forbidden, discord.HTTPException) as exc:
            return False, f"Failed to add to **{slug}**: {exc}"

        self._store.index_upsert(slug, container.id, thread.id)
        self._store.add_enrollment(user.id, slug)
        return True, f"Joined <#{thread.id}> (**{slug}**)."

    async def drop_many(
        self,
        guild: discord.Guild,
        user: discord.abc.User,
        slugs: List[str],
    ) -> Tuple[List[str], List[str]]:
        success, failures = [], []
        term = state.current_term()
        for slug in slugs:
            thread = await self._resolve_thread(guild, slug)
            if not thread:
                self._store.remove_enrollment(user.id, slug)
                failures.append(f"{slug} (not found)")
                continue
            try:
                await thread.remove_user(user)
            except (discord.Forbidden, discord.HTTPException) as exc:
                failures.append(f"{slug} (failed: {exc})")
                continue

            self._store.remove_enrollment(user.id, slug)
            success.append(slug)

            if self._private_containers:
                dept = courses.dept_from_slug(slug)
                if dept:
                    remaining = self._store.courses_by_term_and_dept(user.id, term, dept)
                    if not remaining:
                        container_name = courses.container_name_for(dept.upper(), term=term)
                        container = discord.utils.get(guild.text_channels, name=container_name)
                        if container:
                            try:
                                await container.set_permissions(user, overwrite=None)
                            except (discord.Forbidden, discord.HTTPException):
                                pass
        return success, failures

    async def _resolve_thread(self, guild: discord.Guild, slug: str) -> discord.Thread | None:
        meta = self._store.index_get(slug)
        if meta:
            thread = guild.get_channel(int(meta["thread_id"]))
            if isinstance(thread, discord.Thread):
                return thread
            try:
                fetched = await guild.fetch_channel(int(meta["thread_id"]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                fetched = None
            if isinstance(fetched, discord.Thread):
                return fetched

        dept = courses.dept_from_slug(slug)
        if not dept:
            return None
        container_name = courses.container_name_for(dept.upper(), term=state.current_term())
        container = discord.utils.get(guild.text_channels, name=container_name)
        if not container:
            return None
        for thread in container.threads:
            if thread.name == slug:
                return thread
        return await fetch_archived_thread_by_name(container, slug)

