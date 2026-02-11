import discord
import discord.ui as ui

from Steward.bot import StewardBot
from Steward.models.automation.context import AutomationContext
from Steward.models.automation.utils import eval_numeric
from Steward.models.modals import get_value_modal
from Steward.models.modals.log import LogDetailsModal
from Steward.models.objects.activity import Activity
from Steward.models.objects.character import Character
from Steward.models.objects.enum import LogEvent
from Steward.models.objects.exceptions import StewardError
from Steward.models.objects.log import StewardLog
from Steward.models.objects.player import Player
from Steward.models.objects.servers import Server
from Steward.models.views import StewardView
from Steward.utils.discordUtils import is_admin
from Steward.utils.viewUitils import get_activity_select_option, get_character_select_option, get_player_header

class CreateLogView(StewardView):
    __copy_attrs__ = [
        'bot', 'player', 'server', 'activity', 'notes', 'currency', 'xp', "owner", "character", "admin"
    ]

    def __init__(
            self,
            owner: Player,
            bot: StewardBot,
            player: Player,
            server: Server,
            admin: bool,
            **kwargs
    ):
        self.owner = owner
        self.bot = bot
        self.player = player
        self.server = server
        self.admin = admin

        self.activity: Activity = kwargs.get("activity")
        self.notes = kwargs.get("notes")
        self.currency = kwargs.get('currency')
        self.xp = kwargs.get('xp')

        if len(self.player.active_characters) == 1:
            self.character = self.player.primary_character
        else:
            self.character = kwargs.get('character')

        container = ui.Container(
            get_player_header(self.player),
            ui.Separator(),
            ui.TextDisplay(
                f"**Character**: {self.character.name if self.character else '`None`'}\n"
                f"**Activity**: {self.activity.name if self.activity else '`None`'}"
            )
        )

        if self.activity and self.activity.allow_override == True:
            container.add_item(
                ui.TextDisplay(
                    f"**{self.server.currency_label}**: {self.currency:,}\n"
                    f"**XP**: {self.xp:,}"
                )
            )

        container.add_item(
            ui.TextDisplay(
                f"**Notes**:\n{self.notes}"
            )
        )

        char_select = get_character_select_option(self.player, self.character, self._character_select, enable_def=False)
        activity_select = get_activity_select_option(self.server, self.activity, self._activity_select, admin=admin)

        detail_button = ui.Button(
            label="Details",
            style=discord.ButtonStyle.blurple
        )
        detail_button.callback = self._details_button

        
        submit_button = ui.Button(
            label="Submit",
            style=discord.ButtonStyle.green,
            disabled=False if self.allow_submit() else True
        )
        submit_button.callback = self._submit_button

        cancel_button = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.red
        )
        cancel_button.callback = self.timeout_callback

        super().__init__(
            container,
            ui.ActionRow(char_select),
            ui.ActionRow(activity_select),
            ui.ActionRow(detail_button, submit_button, cancel_button)
        )

    def allow_submit(self) -> bool:
        if not self.activity:
            return False
        
        if not self.character:
            return False
        
        if self.activity and self.activity.allow_override == True and not (self.currency or self.xp):
            return False
        
        return True


    async def _submit_button(self, interaction: discord.Interaction):
        if self.activity and self.activity.allow_override == True:
            modifier = -1 if self.activity.inverse_override == True else 1

            await StewardLog.create(
                self.bot,
                self.owner,
                self.player,
                LogEvent.activity,
                activity=self.activity,
                character=self.character,
                xp=self.xp*modifier,
                currency=self.currency*modifier,
                notes=self.notes
            )
        else:
            await StewardLog.create(
                self.bot,
                self.owner,
                self.player,
                LogEvent.activity,
                activity=self.activity,
                character=self.character,
                notes=self.notes
            )

        await interaction.respond("Activity Logged!", ephemeral=True)

        await self.on_timeout()
            

    async def _details_button(self, interaction: discord.Interaction):
        modal = LogDetailsModal(self.server, self.activity, self.notes, self.currency, self.xp)
        await self.prompt_modal(modal, interaction)

        self.notes = modal.notes
        self.currency = modal.currency
        self.xp = modal.xp

        await self.refresh_content(interaction)

    async def _character_select(self, interaction: discord.Interaction):
        char = interaction.data.get('values')[0]

        self.character = next(
            (c for c in self.player.active_characters if str(c.id) == char),
            None
        )

        await self.refresh_content(interaction)

    async def _activity_select(self, interaction: discord.Interaction):
        act = interaction.data.get('values')[0]

        self.activity = self.server.get_activity(act)

        if self.activity and self.activity.allow_override == True:
            context = AutomationContext(interaction, self.character, self.player, self.server)
            if self.currency is None:
                self.currency = eval_numeric(self.activity.currency_expr, context)

            if self.xp is None:
                self.xp = eval_numeric(self.activity.xp_expr, context)
        
        await self.refresh_content(interaction)
    