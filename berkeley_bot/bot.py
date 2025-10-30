"""Bot factory for the Berkeley enrollment project."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .commands import register_commands
from .config import BotConfig, load_config
from .enrollment import EnrollmentService
from .registration import RegistrationService
from .storage import DataStore


def create_bot() -> tuple[commands.Bot, BotConfig]:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    config = load_config()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    store = DataStore(config.paths)
    registration = RegistrationService(store, config)
    enrollment = EnrollmentService(store, private_containers=config.private_containers)

    register_commands(bot, config, store, registration, enrollment)
    return bot, config

