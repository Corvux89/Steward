import discord
import discord.ui as ui

from Steward.bot import StewardBot
from Steward.models.objects.application import Application, ApplicationTemplate
from Steward.models.objects.enum import RuleTrigger
from Steward.models.objects.player import Player
from Steward.utils.discordUtils import get_webhook
from Steward.utils.viewUitils import get_character_select_option


class ApplicationModal(ui.DesignerModal):
    bot: StewardBot
    application: Application
    message: discord.Message

    def __init__(self, bot: "StewardBot", player: "Player", template: ApplicationTemplate, **kwargs):
        self.bot = bot
        self.player = player
        self.message = kwargs.get('message')
        content = []

        self.application = kwargs.get(
            'application',
            Application(player, template)
        )

        if self.application.template.character_specific == True:
            character_select = ui.Label(
                "Select a character",
                get_character_select_option(self.player, self.application.character if self.application.character else None, None, enable_def=False)
            )
            content.append(character_select)

        application_input = ui.Label(
            "Application",
            ui.InputText(
                placeholder="",
                value=self.application.content if self.application.content != '' else self.application.template.template,
                style=discord.InputTextStyle.long,
                custom_id="application"
            )
        )
        content.append(application_input)

        super().__init__(
            *content,
            title=f"{self.application.template.name} Application"
        )

    async def callback(self, interaction: discord.Interaction):
        self.application.content = self.get_item('application').value
        
        if self.application.template.character_specific == True:
            char_id = self.get_item('char_select').values[0]
            self.application.character = next(
                (c for c in self.player.active_characters if str(c.id) == char_id),
                None
            )
        
        if self.message:
            webhook = await get_webhook(self.message.channel)
            await webhook.edit_message(self.message.id, content=self.application.output)
            await interaction.response.send_message("Application edited!", ephemeral=True)
        else:
            await interaction.response.send_message("Application completed!", ephemeral=True)
            self.bot.dispatch(RuleTrigger.new_application.name, application=self.application)

        self.stop()
        