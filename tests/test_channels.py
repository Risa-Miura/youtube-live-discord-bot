"""Administrator access and notification destination tests, without network calls."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot import NotificationBot
from config import Settings
from notifications import LiveStream, notification_channel
from state import StateError, StateStore


class ChannelStateTests(unittest.TestCase):
    def test_independent_settings_and_guilds_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory))
            store.set_channel(1, 10)
            store.set_role(2, 20)
            store = StateStore(Path(directory))
            self.assertEqual(store.notification_channel_id(1), 10)
            self.assertIsNone(store.notification_channel_id(2))
            store.set_role(1, 30)
            store.set_channel(2, 40)
            store.set_channel(1, 50)
            self.assertEqual(StateStore(Path(directory)).destinations(), {
                "1": {"channel_id": 50, "role_id": 30},
                "2": {"role_id": 20, "channel_id": 40},
            })

    def test_failed_channel_save_keeps_memory_and_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory))
            store.set_channel(1, 10)
            with patch("state.os.fsync", side_effect=OSError):
                with self.assertRaises(StateError):
                    store.set_channel(1, 99)
            self.assertEqual(store.notification_channel_id(1), 10)
            self.assertEqual(StateStore(Path(directory)).notification_channel_id(1), 10)


class AdminAndChannelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.bot = NotificationBot(Settings("token", "key", "UCexample", "https://twitch.tv/example", Path(directory.name)))
        self.addAsyncCleanup(self.bot.close)
        self.guild = MagicMock(id=1, owner_id=7)
        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.id = 10
        self.channel.mention = "<#10>"
        self.channel.guild = self.guild
        self.channel.send = AsyncMock()
        self.channel.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True)
        self.guild.get_channel.return_value = self.channel

    def interaction(self, user_id=7, guild=True, administrator=True, manage_guild=False):
        return SimpleNamespace(
            guild=self.guild if guild else None, guild_id=1 if guild else None,
            user=SimpleNamespace(id=user_id, guild_permissions=discord.Permissions(
                administrator=administrator, manage_guild=manage_guild,
            )),
            response=AsyncMock(), followup=AsyncMock(),
            data={"name": "set-channel", "type": 1, "options": []},
            type=discord.InteractionType.application_command,
            _state=self.bot._connection, command_failed=False,
        )

    async def test_owner_and_administrator_can_execute_and_future_commands_inherit_policy(self):
        @self.bot.tree.command(name="future-command")
        async def future(interaction: discord.Interaction):
            await interaction.response.send_message("Executed")

        # Discord resolves the owner's guild permissions to include Administrator.
        for user_id in (self.guild.owner_id, 8):
            with self.subTest(user=user_id):
                interaction = self.interaction(user_id=user_id)
                interaction.data["name"] = "future-command"
                await self.bot.tree._call(interaction)
                interaction.response.send_message.assert_awaited_once_with("Executed")
        self.assertTrue(future.guild_only)
        self.assertEqual(future.default_permissions, discord.Permissions(administrator=True))

    async def test_nonadmins_and_dms_cannot_dispatch_or_change_state(self):
        self.bot.store.set_channel(1, 10)
        before = (self.bot.store.directory / "role_config.json").read_bytes()
        for user_id, guild, admin, manage in (
            (8, True, False, True), (9, True, False, False), (7, False, True, True),
        ):
            for command in self.bot.tree.get_commands():
                with self.subTest(user=user_id, guild=guild, command=command.name):
                    interaction = self.interaction(user_id, guild, admin, manage)
                    interaction.data["name"] = command.name
                    # Exercise discord.py's dispatch boundary: denial must happen before resolution/handlers.
                    with patch.object(self.bot.tree, "_get_app_command_options") as resolve:
                        await self.bot.tree._call(interaction)
                        resolve.assert_not_called()
                    self.assertTrue(interaction.command_failed)
                    interaction.response.send_message.assert_awaited_once_with(
                        "Only server administrators can use this command." if guild else "Commands can only be used in a server.",
                        ephemeral=True,
                    )
        self.assertEqual((self.bot.store.directory / "role_config.json").read_bytes(), before)
        self.assertEqual(self.bot.store.notification_channel_id(1), 10)

    async def test_set_channel_selector_and_owner_success(self):
        command = self.bot.tree.get_command("set-channel")
        self.assertEqual(command.parameters[0].type, discord.AppCommandOptionType.channel)
        self.assertEqual(command.parameters[0].channel_types, [discord.ChannelType.text, discord.ChannelType.news])
        interaction = self.interaction()
        self.assertTrue(await self.bot.tree.interaction_check(interaction))
        await command.callback(interaction, self.channel)
        self.assertEqual(StateStore(self.bot.store.directory).notification_channel_id(1), 10)
        self.assertEqual(interaction.response.send_message.await_args.args[0], "Notification channel set to <#10>.")

    async def test_unusable_channel_is_not_saved(self):
        for view, send in ((False, True), (True, False), (False, False)):
            self.channel.permissions_for.return_value = discord.Permissions(view_channel=view, send_messages=send)
            interaction = self.interaction()
            await self.bot.tree.get_command("set-channel").callback(interaction, self.channel)
            self.assertIsNone(self.bot.store.notification_channel_id(1))
            self.assertIn("View Channel and Send Messages", interaction.response.send_message.await_args.args[0])

    async def test_missing_deleted_and_inaccessible_destinations_skip_alerts(self):
        self.guild.get_role.return_value = SimpleNamespace(id=2, mention="<@&2>")
        self.bot.store.set_role(1, 2)
        stream = LiveStream("video", "Stream", "https://youtube.com/watch?v=video")
        with patch.object(type(self.bot), "guilds", new_callable=lambda: property(lambda _: [self.guild])):
            for condition in ("unset", "deleted", "inaccessible"):
                if condition != "unset":
                    self.bot.store.set_channel(1, 10)
                self.guild.get_channel.return_value = None if condition == "deleted" else self.channel
                if condition == "inaccessible":
                    self.channel.permissions_for.return_value = discord.Permissions.none()
                with self.assertLogs("notifications", level="WARNING") as logs:
                    self.assertEqual(await self.bot.notifier.announce(stream), 0)
                self.assertIn("/set-channel", str(logs.output))
                self.assertFalse(self.bot.store.was_announced("1", "video"))
            self.channel.send.assert_not_awaited()

    async def test_saved_destination_changes_delivery_and_role_change_does_not_move_it(self):
        self.bot.store.set_channel(1, 10)
        interaction = self.interaction()
        await self.bot.tree.get_command("set-role").callback(
            interaction, SimpleNamespace(id=2, mention="<@&2>", is_default=lambda: False)
        )
        self.assertEqual(self.bot.store.notification_channel_id(1), 10)
        self.bot.store.set_channel(1, 20)
        self.assertIs(notification_channel(self.guild, self.bot.store), self.channel)
        self.guild.get_channel.assert_called_with(20)

    async def test_save_error_is_reported_privately(self):
        interaction = self.interaction()
        with patch.object(self.bot.store, "set_channel", side_effect=StateError("Cannot save role_config.json.")):
            await self.bot.tree.get_command("set-channel").callback(interaction, self.channel)
        interaction.response.send_message.assert_awaited_once_with("Cannot save role_config.json.", ephemeral=True)
