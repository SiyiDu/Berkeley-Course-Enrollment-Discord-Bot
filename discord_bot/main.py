"""Entry point for the Discord bot."""

from __future__ import annotations

from .bot import create_bot


def main() -> None:
    bot, config = create_bot()
    bot.run(config.token)


if __name__ == "__main__":
    main()
