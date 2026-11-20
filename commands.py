"""Slash commands translate Discord interactions into service calls."""

import discord
from discord import app_commands

from notifications import LiveNotifier, channel_permission_error
from state import StateError


class AdminCommandTree(app_commands.CommandTree):
    """Require guild Administrator permission before dispatching any command."""

    def add_command(self, command, /, **kwargs) -> None:
        command.guild_only = True
        command.default_permissions = discord.Permissions(administrator=True)
        super().add_command(command, **kwargs)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            message = "Commands can only be used in a server."
        elif not interaction.user.guild_permissions.administrator:
            message = "Only server administrators can use this command."
        else:
            return True
        await interaction.response.send_message(message, ephemeral=True)
        return False


def register_commands(tree: app_commands.CommandTree, notifier: LiveNotifier) -> None:
    @tree.command(name="ping", description="Check whether the bot is responding.")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Pong!")

    @tree.command(name="set-channel", description="Choose the channel for all notifications.")
    @app_commands.describe(channel="The text channel where notifications will be sent")
    async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if interaction.guild is None:
            return
        error = channel_permission_error(channel, interaction.guild)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        try:
            notifier.store.set_channel(interaction.guild.id, channel.id)
        except StateError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Notification channel set to {channel.mention}.", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @tree.command(name="set-role", description="Choose the role used for notifications.")
    @app_commands.describe(role="The role to ping for notifications")
    async def set_role(interaction: discord.Interaction, role: discord.Role) -> None:
        if role.is_default():
            await interaction.response.send_message("Choose a role other than @everyone.", ephemeral=True)
            return
        if interaction.guild_id is None:
            return
        try:
            notifier.store.set_role(interaction.guild_id, role.id)
        except StateError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Notification role set to {role.mention}. Use `/set-channel` to choose the destination.",
            allowed_mentions=discord.AllowedMentions.none(), ephemeral=True,
        )

    @tree.command(name="test-live", description="Send a test livestream notification.")
    async def test_live(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            return
        try:
            sent = await notifier.send_test(interaction.guild_id)
            message = (
                "Test notification sent using the live notification function."
                if sent else
                "I could not send the test. Configure `/set-channel` and `/set-role`, and check bot permissions."
            )
        except (ValueError, StateError) as error:
            message = str(error)
        await interaction.followup.send(message, ephemeral=True)
