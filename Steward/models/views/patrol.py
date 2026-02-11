import discord
import discord.ui as ui

from Steward.models.modals import get_character_select_modal
from Steward.models.objects.exceptions import StewardError
from Steward.models.views import StewardView, confirm_view
from Steward.utils.discordUtils import is_admin
from constants import DENIED_EMOJI

from ...bot import StewardBot
from ..objects.patrol import Patrol


class PatrolView(StewardView):
    __copy_attrs__ = [
        "bot", "patrol"
    ]

    async def interaction_check(self, _: discord.Interaction):
        return True

    def __init__(self, bot: "StewardBot", patrol: "Patrol"):
        self.bot = bot
        self.patrol = patrol

        container = ui.Container(
            ui.TextDisplay("## Patrol Information"),
            ui.Separator()
        )

        if self.patrol.notes and self.patrol.notes != "":
            container.add_item(
                ui.TextDisplay(self.patrol.notes)
            )
            container.add_item(ui.Separator())


        container.add_item(
            ui.TextDisplay("### Participants")
        )
        
        container.add_item(
            ui.TextDisplay(
                f"**Host**: {self.patrol.host.mention}\n\n**Players**:\n"
            )
        )

        for character in self.patrol.characters:
            member = self.patrol.channel.guild.get_member(character.player_id)
            remove_button = ui.Button(
                emoji= DENIED_EMOJI[0],
                custom_id=str(character.id)
            )
            remove_button.callback = self._remove_character

            container.add_item(
                ui.Section(
                    ui.TextDisplay(
                        f" - {character.name} ({member.mention})"
                    ),
                    accessory=remove_button
                )
            )

        join_button = ui.Button(
            style=discord.ButtonStyle.blurple,
            label="Join",
            custom_id="join_patrol"
        )
        join_button.callback = self._join_patrol

        super().__init__(
            container,
            ui.ActionRow(join_button),
            timeout=None,
        )

    async def _join_patrol(self, interaction: discord.Interaction):
        from .player import Player
        if interaction.user.id == self.patrol.host.id:
            await interaction.response.send_message("You are hosting this patrol", ephemeral=True)
        elif interaction.user.id in [c.player_id for c in self.patrol.characters]:
            await interaction.response.send_message("You are already in this patrol. Remove a character first", ephemeral=True)
        
        member = self.patrol.channel.guild.get_member(interaction.user.id)
        player = await Player.get_or_create(self.bot.db, member)

        if not player.active_characters:
            await interaction.response.send_message("You have no characters to join the patrol with", ephemeral=True)

        if len(player.active_characters) == 1:
            self.patrol.characters.append(player.primary_character)
            await self.patrol.upsert()
        else:
            character = await get_character_select_modal(
                interaction,
                player.active_characters
            )

            if character:
                self.patrol.characters.append(character)
                await self.patrol.upsert()
        
        await self.refresh_content(interaction)

    async def _remove_character(self, interaction: discord.Interaction):
        char = interaction.data.get('custom_id')
        await interaction.response.defer()

        character = next(
            (c for c in self.patrol.characters if str(c.id) == char),
            None
        )

        if not character:
            await interaction.response.send_message("Character not found", ephemeral=True)
        elif interaction.user.id not in [self.patrol.host.id, character.player_id] or not is_admin(interaction):
            await interaction.response.send_message("You cannot remove this character", ephemeral=True)

        if await confirm_view(
            interaction,
            f"Are you sure you want to remove {character.name} from this patrol?"
        ) == True:
            self.patrol.characters.remove(character)
            await self.patrol.upsert()

        await self.refresh_content(interaction)

