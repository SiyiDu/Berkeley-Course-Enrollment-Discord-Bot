"""Entry point for the Berkeley enrollment Discord bot."""

from berkeley_bot import create_bot


def main() -> None:
    bot, config = create_bot()
    bot.run(config.token)


if __name__ == "__main__":
    main()

