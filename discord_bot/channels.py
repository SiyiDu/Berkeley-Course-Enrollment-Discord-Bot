"""Discord channel helpers."""

from __future__ import annotations

from typing import Optional

import discord

async def ensure_category(guild: discord.Guild, name: str) -> discord.CategoryChannel:
    category = discord.utils.get(guild.categories, name=name)
    if category:
        return category
    return await guild.create_category(name)


async def ensure_container_text_channel(
    guild: discord.Guild,
    parent: discord.CategoryChannel,
    name: str,
) -> discord.TextChannel:
    channel = discord.utils.get(guild.text_channels, name=name)
    if channel:
        if channel.category_id != parent.id:
            await channel.edit(category=parent)
        return channel
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    return await guild.create_text_channel(name, category=parent, overwrites=overwrites)


async def fetch_archived_thread_by_name(
    container: discord.TextChannel, name: str
) -> Optional[discord.Thread]:
    for is_private in (False, True):
        try:
            async for thread in container.archived_threads(limit=None, private=is_private):
                if thread.name == name:
                    return thread
        except discord.Forbidden:
            continue
    return None


async def ensure_private_course_thread(
    container: discord.TextChannel,
    slug: str,
) -> discord.Thread:
    existing = discord.utils.get(container.threads, name=slug)
    if existing:
        return existing

    archived = await fetch_archived_thread_by_name(container, slug)
    if archived:
        await archived.edit(archived=False, locked=False)
        return archived

    return await container.create_thread(
        name=slug,
        type=discord.ChannelType.private_thread,
        invitable=False,
    )
