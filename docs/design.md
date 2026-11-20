# State and reliability

How the bot stores state, avoids duplicate alerts, and handles failures, plus
the known limits of the YouTube detector.

Existing root-level JSON files retain their names and formats; upgrading does
not require migration. State is loaded at startup and updated by the bot.
Restart after manually editing a state file. To change `DATA_DIR`, stop the bot
and copy both existing JSON files into that directory first.

`/set-channel` saves `channel_id` per server in the existing `role_config.json`.
This is the shared destination for all current notifications, including `/test-live`;
future notification sources should use `notification_channel()` in `notifications.py`.
The setting persists across bot/container restarts, VM reboots, and Compose rebuilds
because Compose stores the file in its existing `/data` named volume. Existing saved
channels remain valid; no new environment variable or migration is needed.

`/set-role` now changes only the role. For a new server, both settings must be
configured before livestream alerts can be sent. An unset, deleted, or inaccessible
channel causes a warning and skips delivery without falling back to another channel.
Fix the bot's permissions if necessary, then use `/set-channel` to select a usable
destination. Unsent streams are not marked as announced.

JSON saves use a temporary file and atomic replacement. Malformed or unreadable
state causes a clear startup error instead of silently forgetting announcements;
repair the file or restore a backup. Missing files are treated as a new setup.

Temporary YouTube/network errors are logged without API keys and retried on the
next poll. Discord send failures do not mark a stream as announced. A successful
alert is saved immediately for that server.

Run one bot instance against a given state directory. JSON state cannot make the
Discord send and disk write one transaction: a crash between them, a disk failure,
or deleting the state file can still cause a repeat after restart. Keep backups.

The existing detector checks the latest 50 activity entries for active videos.
It is not a guaranteed real-time feed: YouTube indexing delays or absent activity
entries can delay or miss alerts. An already-live, previously unannounced stream
may be announced at startup. This refactor keeps that detection behavior.
