import discord
import discord.ui as ui

from Steward.bot import StewardBot
from Steward.models.automation.context import AutomationContext
from Steward.models.automation.utils import eval_numeric
from Steward.models.objects.activity import Activity
from Steward.models.objects.character import Character
from Steward.models.objects.enum import LogEvent
from Steward.models.objects.exceptions import StewardError
from Steward.models.objects.log import StewardLog
from Steward.models.objects.player import Player
from Steward.models.objects.servers import Server
from Steward.utils.viewUitils import get_activity_select_option, get_character_select_option

class LogDetailsModal(ui.DesignerModal):
    def __init__(
            self,
            server: Server,
            activity: Activity,
            notes: str,
            currency: float,
            xp:float
    ):
        self.server = server
        self.activity = activity
        self.notes = notes
        self.currency = currency
        self.xp = xp

        content = []

        if self.activity and self.activity.allow_override == True:
            currency_input = ui.Label(
                self.server.currency_label,
                ui.TextInput(
                    custom_id="currency",
                    value=str(self.currency)
                )
            )
            content.append(currency_input)

            xp_input = ui.Label(
                "XP",
                ui.TextInput(
                    custom_id="xp",
                    value=str(self.xp)
                )
            )
            content.append(xp_input)

        notes_input = ui.Label(
            "Notes",
            ui.TextInput(
                style=discord.InputTextStyle.long,
                required=False,
                custom_id="notes",
                value=self.notes
            )
        )
        content.append(notes_input)

        super().__init__(
            *content,
            title="Log Details"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            self.xp = float(self.get_item("xp").value)
            self.currency = float(self.get_item("currency").value)
            self.notes = self.get_item("notes").value
        except:
            pass
        
        await interaction.response.defer()
        self.stop()