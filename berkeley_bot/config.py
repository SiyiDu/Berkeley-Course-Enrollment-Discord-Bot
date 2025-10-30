"""Runtime configuration for the Berkeley enrollment bot."""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

from dotenv import load_dotenv


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _env_flag(name: str, *, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PathConfig:
    course_index: pathlib.Path
    enrollments: pathlib.Path
    users: pathlib.Path


@dataclass(frozen=True)
class BotConfig:
    token: str
    guild_id: int
    student_role_name: str
    berkeley_suffix: str
    private_containers: bool
    paths: PathConfig


def load_config() -> BotConfig:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing in .env")

    guild_id = int(os.getenv("GUILD_ID", "1432284673865682959"))
    student_role_name = os.getenv("STUDENT_ROLE_NAME", "student")
    berkeley_suffix = os.getenv("BERKELEY_SUFFIX", "@berkeley.edu")
    private_containers = _env_flag("PRIVATE_CONTAINERS", default=True)

    paths = PathConfig(
        course_index=PROJECT_ROOT / "course_index.json",
        enrollments=PROJECT_ROOT / "enrollments.json",
        users=PROJECT_ROOT / "users.json",
    )

    return BotConfig(
        token=token,
        guild_id=guild_id,
        student_role_name=student_role_name,
        berkeley_suffix=berkeley_suffix,
        private_containers=private_containers,
        paths=paths,
    )

