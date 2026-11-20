"""The shared path for real livestream alerts and /test-live."""

import asyncio
import logging
from dataclasses import dataclass

import discord

from config import Settings
from state import StateStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveStream:
    video_id: str
    title: str
    url: str


def _escape(text: str) -> str:
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text))


def format_live_notification(
    stream: LiveStream, role_mention: str, twitch_url: str, streamer_name: str = "",
) -> str:
    title = _escape(stream.title)
    who = f"{_escape(streamer_name)} is streaming" if streamer_name else "Now streaming"
    return (
        f"🔔 {role_mention} boop!\n"
        f'{who} "**{title}**" '
        f"live on [YouTube]({stream.url}) and "
        f"[Twitch](<{twitch_url}>) ! (,,⟡o⟡,,)"
    )


def channel_permission_error(channel: discord.TextChannel, guild: discord.Guild) -> str | None:
    if channel.guild.id != guild.id:
        return "Choose a text channel in this server."
    if guild.me is None:
        return "I could not verify my channel permissions. Please try again."
    permissions = channel.permissions_for(guild.me)
    if not permissions.view_channel or not permissions.send_messages:
        return "I need View Channel and Send Messages permissions in that channel."
    return None


def notification_channel(guild: discord.Guild, store: StateStore) -> discord.TextChannel | None:
    """Resolve the shared destination for any notification source, without a fallback."""
    channel_id = store.notification_channel_id(guild.id)
    if channel_id is None:
        logger.warning("No notification channel configured in guild %s; use /set-channel", guild.id)
        return None
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        logger.warning("Notification channel missing in guild %s; use /set-channel", guild.id)
        return None
    if channel_permission_error(channel, guild):
        logger.warning("Notification channel inaccessible in guild %s; check permissions and use /set-channel", guild.id)
        return None
    return channel


class LiveNotifier:
    def __init__(self, client: discord.Client, settings: Settings, store: StateStore):
        self.client = client
        self.settings = settings
        self.store = store
        self._lock = asyncio.Lock()

    async def announce(
        self, stream: LiveStream, guild_ids: set[str] | None = None,
        remember: bool = True,
    ) -> int:
        if not self.settings.twitch_stream_url:
            logger.warning("Cannot send live notification: set TWITCH_STREAM_URL")
            return 0
        sent_count = 0
        async with self._lock:
            destinations = self.store.destinations()
            for guild in self.client.guilds:
                guild_id = str(guild.id)
                if guild_ids is not None and guild_id not in guild_ids:
                    continue
                if remember and self.store.was_announced(guild_id, stream.video_id):
                    continue
                channel = notification_channel(guild, self.store)
                if channel is None:
                    continue
                role_id = destinations.get(guild_id, {}).get("role_id")
                role = guild.get_role(role_id) if role_id is not None else None
                if role is None:
                    logger.warning("Notification role unavailable in guild %s; use /set-role", guild_id)
                    continue
                try:
                    await channel.send(
                        format_live_notification(
                            stream, role.mention, self.settings.twitch_stream_url,
                            self.settings.streamer_name,
                        ),
                        allowed_mentions=discord.AllowedMentions(
                            roles=[role], users=False, everyone=False, replied_user=False,
                        ),
                    )
                except discord.HTTPException as error:
                    logger.warning("Discord alert failed in guild %s (HTTP %s); check permissions and use /set-channel if needed", guild_id, error.status)
                    continue
                sent_count += 1
                if remember:
                    self.store.mark_announced(guild_id, stream.video_id)
        return sent_count

    async def send_test(self, guild_id: int) -> int:
        if not self.settings.youtube_channel_id:
            raise ValueError("Set YOUTUBE_CHANNEL_ID in your .env file before testing.")
        if not self.settings.twitch_stream_url:
            raise ValueError("Set TWITCH_STREAM_URL in your .env file before testing.")
        stream = LiveStream(
            "test-live-notification", "Test livestream notification",
            f"https://www.youtube.com/channel/{self.settings.youtube_channel_id}/live",
        )
        return await self.announce(stream, guild_ids={str(guild_id)}, remember=False)
