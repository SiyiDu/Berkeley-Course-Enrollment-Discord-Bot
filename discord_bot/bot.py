"""Bot factory for the Berkeley enrollment project."""

from __future__ import annotations

import logging
import os

import discord
from discord.ext import commands

from .commands import register_commands
from .config import BotConfig, load_config
from .enrollment import EnrollmentService
from .registration import RegistrationService
from .storage import DataStore


def create_bot() -> tuple[commands.Bot, BotConfig]:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    config = load_config()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    if config.storage_backend == "db" and not config.bot_database_url:
        raise RuntimeError("BOT_DATABASE_URL is required when BOT_STORAGE_BACKEND=db")
    db_url = config.bot_database_url if config.storage_backend == "db" else None
    store = DataStore(
        config.paths,
        database_url=db_url,
        db_connect_timeout=config.db_connect_timeout,
        db_max_retries=config.db_max_retries,
        db_retry_backoff_sec=config.db_retry_backoff_sec,
    )
    registration = RegistrationService(store, config)
    enrollment = EnrollmentService(store, private_containers=config.private_containers)

    register_commands(bot, config, store, registration, enrollment)
    return bot, config
