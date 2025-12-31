import discord
import logging
import sys

from discord.ext import commands

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class MyHelpCommand(commands.MinimalHelpCommand):
    async def send_pages(self):
        destination = self.get_destination()
        embed = discord.Embed(
            color=discord.Color.blurple(),
            description=""
        )

        for page in self.paginator.pages:
            embed.description += page
        
        await destination.send(embed=e)

log_formatter = logging.Formatter("%(asctime)s %(name)s: %(message)s")
handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger()
logger.setLevel(logging.ERROR if not DEBUG else logging.DEBUG)