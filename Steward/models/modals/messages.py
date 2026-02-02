import discord
import discord.ui as ui

from ...bot import StewardBot
from ..objects.webhook import StewardWebhook

class SayEditModal(ui.DesignerModal):
    bot: StewardBot
    webhook: StewardWebhook

    def __init__(self, bot: StewardBot, webhook: StewardWebhook):
        self.bot = bot
        self.webhook = webhook

        input_1 = ui.Label(
            "Message Content",
            ui.InputText(
                placeholder="",
                value=self.webhook.message.content,
                style=discord.InputTextStyle.long,
                max_length=2000,
                custom_id="message_content"
            )
        )
        
        super().__init__(
            input_1,
            title="Edit Message"
        )

    async def callback(self, interaction: discord.Interaction):
        content = self.get_item("message_content").value
        await interaction.response.defer()
        self.stop()
        await self.webhook.edit(content)