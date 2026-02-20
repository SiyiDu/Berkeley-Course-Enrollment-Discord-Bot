FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY discord_bot/requirements.txt discord_bot/requirements.txt
RUN pip install --no-cache-dir -r discord_bot/requirements.txt

COPY discord_bot /app/discord_bot
COPY shared /app/shared

CMD ["python", "-m", "discord_bot.main"]
