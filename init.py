import asyncio
from os import listdir
import discord
import logging
import sys

from discord.ext import commands
from Steward.bot import StewardBot
from constants import BOT_TOKEN, DEBUG, DEFAULT_PREFIX

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
        
        await destination.send(embed=embed)

log_formatter = logging.Formatter("%(asctime)s %(name)s: %(message)s")
handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger()
logger.setLevel(logging.ERROR if not DEBUG else logging.DEBUG)
logger.addHandler(handler)
log = logging.getLogger("bot")

# # Because Windows is terrible
if sys.version_info >= (3, 8) and sys.platform.lower().startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

bot = StewardBot(
    command_prefix=DEFAULT_PREFIX,
    description="A good game needs a good Steward. Created and maintained by Corvux",
    case_insensitive=True,
    help=MyHelpCommand(),
    intents=intents
)

for filename in listdir("Steward/cogs"):
    if filename.endswith(".py"):
        bot.load_extension(f"Steward.cogs.{filename[:-3]}")

@bot.command()
async def ping(ctx: discord.ApplicationContext):
    print("Pong")
    await ctx.send(f"Pong! Latency is {round(bot.latency * 1000)}ms.")

bot.run(BOT_TOKEN)
