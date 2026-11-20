# YouTube Live Discord Bot

Discord bot that posts an alert when a YouTube channel goes live, pinging a chosen
role with links to the stream on YouTube and Twitch. Works with any YouTube channel
and any Discord server you administer.

![Livestream alert in Discord](docs/screenshots/live-alert.png)

## Requirements

- **Software.** Python 3.12+ with `discord.py`, `aiohttp`, and `python-dotenv`
(see `requirements.txt`), or Docker Compose.
- **Credentials.** A Discord bot token, a YouTube Data API v3 key, the YouTube
channel ID (`UC…`), and a Twitch channel URL. See [docs/setup.md](docs/setup.md)
for how to get each one and which Discord permissions the bot needs.

## Run

```bash
git clone https://github.com/Risa-Miura/youtube-live-discord-bot.git
cd youtube-live-discord-bot
cp .env.example .env    # fill in your values; never commit .env
docker compose up -d --build
```

Then, as a server administrator, run `/set-channel`, `/set-role`, and `/test-live`
in Discord.

Polls the YouTube Data API v3 every 60 seconds and posts each live stream once per
server, remembering the last 100 announced stream IDs across restarts. Twitch is a
link in the alert, not a separate live detector.

Running without Docker: [docs/setup.md](docs/setup.md#run-locally). Deploying to a
Google Cloud VM: [docs/deployment.md](docs/deployment.md). State, duplicate
prevention, and failure handling: [docs/design.md](docs/design.md).

## Commands

All commands require the Administrator permission and only work inside a server.

| Command | Description |
|---------|-------------|
| `/set-channel` | Choose the text channel for alerts |
| `/set-role` | Choose the role to ping |
| `/test-live` | Send a test alert through the same path as real streams (pings the role) |
| `/ping` | Check that the bot is responding |

## Tests

```bash
python -m unittest discover -s tests -v
```

Run inside a virtual environment with `requirements.txt` installed. The tests make
no live API calls and never read your real `.env`.

## Project structure

- `bot.py` — entry point
- `commands.py` — slash commands
- `notifications.py` — alert formatting and delivery
- `state.py` — JSON state storage
- `monitors/` — YouTube polling
- `tests/` — unit tests
- `docs/` — setup, deployment, and design notes
