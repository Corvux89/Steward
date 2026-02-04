import discord
import discord.ui as ui

from Steward.bot import StewardBot
from Steward.models.objects.activity import Activity
from Steward.models.objects.character import Character
from Steward.models.objects.enum import LogEvent
from Steward.models.objects.exceptions import StewardError
from Steward.models.objects.log import StewardLog
from Steward.models.objects.player import Player
from Steward.models.objects.servers import Server
from Steward.utils.viewUitils import get_activity_select_option, get_character_select_option

class RewardModal(ui.DesignerModal):
    player: Player
    server: Server
    character: Character
    bot: StewardBot

    def __init__(
            self,
            bot: StewardBot,
            player: Player,
            server: Server
    ):
        self.bot = bot
        self.player = player
        self.server = server

        if len(self.player.active_characters) == 1:
            self.character = self.player.active_characters[0]
        else:
            self.character = None


        char_select = get_character_select_option(self.player, self.character, default_label="Select a Character", enable_def=False)

        character_input = ui.Label(
            "Character",
            char_select
        )

        act_select = get_activity_select_option(self.server, enable_def=False)

        activity_input = ui.Label(
            "Activity",
            act_select
        )

        notes_input = ui.Label(
            "Notes",
            ui.TextInput(
                style=discord.InputTextStyle.long,
                max_length=4000,
                required=False,
                custom_id="log_notes"
            )
        )

        super().__init__(
            character_input,
            activity_input,
            notes_input,
            title="Character Reward"
        )        

    async def callback(self, interaction):
        act = self.get_item("activity_select").values[0]
        char = self.get_item("char_select").values[0]
        notes = self.get_item("log_notes").value

        character = next(
            (c for c in self.player.active_characters if str(c.id) == char),
            None
        )

        if character is None:
            raise StewardError("You need to specify a character to reward")

        activity = next(
            (a for a in self.server.activities if a.name == act),
            None
        )

        if activity is None:
            raise StewardError("You need to specify an activity")
        
        log_entry = await StewardLog.create(
            self.bot,
            interaction.user,
            self.player,
            LogEvent.activity,
            activity=activity,
            character=character,
            notes=notes
        )

        await interaction.respond(f"Activity Logged!", ephemeral=True)
        self.stop()