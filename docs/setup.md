# Setup and configuration

Full setup for running the bot from source. For the short version, see the
[Run section in the README](../README.md#run). For Docker Compose and VM deployment, see
[deployment.md](deployment.md).

## Requirements and external APIs

- Python 3.12 or newer; Docker uses Python 3.12.
- A Discord application and bot token.
- For automatic monitoring: a YouTube Data API v3 key, the actual YouTube channel
  ID (starting with `UC`), and a Twitch channel URL.
- Outbound internet access to Discord and Google's YouTube API.

Dependencies are `discord.py`, `python-dotenv`, and `aiohttp`. The tests use
Python's built-in `unittest` and make no live API requests.

## Setup

Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
Obtain its token on the Bot page. Invite it to your server using the `bot` and
`applications.commands` scopes. Grant **View Channels**, **Send Messages**, and
**Embed Links** in the destination channel. No privileged gateway intents are needed.

For a role ping to notify members, make the role mentionable or grant the bot
**Mention @everyone, @here, and All Roles**.

Every slash command requires Discord's **Administrator** permission, including
`/ping`, `/set-channel`, `/set-role`, and `/test-live`. This includes the server owner,
whose guild permissions inherently include Administrator. **Manage Server** alone
is not enough. A shared command-tree check verifies the caller's guild permissions
before dispatch, including for future commands registered on the tree.
Commands outside a server are rejected privately.

Commands are registered as guild-only with Administrator default permissions to
limit availability in Discord. Server-specific command overrides may still make
commands visible; visibility is not guaranteed. The runtime permission check
still denies non-administrators even if Discord lets them invoke a command. See discord.py's
[command tree interaction check](https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.app_commands.CommandTree.interaction_check).

Enable **YouTube Data API v3** in a Google Cloud project and create an API key.
Restrict that key to the YouTube Data API. See the
[official setup guide](https://developers.google.com/youtube/v3/getting-started).
Use a channel ID, not a handle or URL; a channel URL in the form
`youtube.com/channel/UC...` contains the ID.

### Windows PowerShell

Run from the project directory. Skip creating the virtual environment if it
already exists.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you do not already have a `.env` file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally. Keep your existing file when upgrading.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `DISCORD_TOKEN` | Required bot token. Never share or commit it. |
| `YOUTUBE_API_KEY` | API key for YouTube Data API v3. |
| `YOUTUBE_CHANNEL_ID` | Actual channel ID; handle conversion is not supported. |
| `TWITCH_STREAM_URL` | Full Twitch channel URL included in each alert. |
| `STREAMER_NAME` | Optional name shown in alerts ("<name> is streaming"). Without it alerts say "Now streaming". |
| `DATA_DIR` | Optional state directory. Defaults to the project directory locally and `/data` in Docker. |

All three monitoring values must be set to enable YouTube polling. Without
them the bot still connects and `/ping` works; startup logs name the missing
settings. `/test-live` needs the channel ID and Twitch URL but does not call
YouTube. Example placeholders are treated as missing values.

Settings load once at startup from the `.env` beside `bot.py`. Existing process
environment variables take precedence. Relative `DATA_DIR` paths resolve from
the project directory. Restart the bot after editing settings.

## Run locally

Windows:

```powershell
.\.venv\Scripts\python.exe bot.py
```

Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python bot.py
```

Wait for the connected message in the terminal. As a server administrator, run
`/set-channel` and select a text channel using Discord's channel selector. The bot
must have **View Channel** and **Send Messages** there. Then run `/set-role`
to select the livestream role, followed by `/test-live`. The test
really mentions that role and can be repeated; it does not change the saved
stream history. Global command updates can take time to appear.

The notification text and clickable link formatting are kept in
`format_live_notification()` in `notifications.py`. Both real streams and
tests call `LiveNotifier.announce()`.

Press **Ctrl+C** to stop locally. Linux/Docker SIGTERM also closes the polling
task, HTTP session, and Discord connection.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

On Linux use `.venv/bin/python` in place of the Windows executable.

Tests cover configuration, the exact notification text, role mention restrictions,
state compatibility and restart deduplication, failed delivery retries,
concurrent delivery, the four slash commands, administrator-only dispatch (including
server owners, Manage Server without Administrator, and DMs), per-server channel persistence and permissions,
live-video filtering, API failure
recovery, sanitized errors, and HTTP-session cleanup. They use temporary state
directories and never read your real `.env`.
