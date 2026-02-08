from contextlib import redirect_stdout
import io
import logging
import textwrap
import traceback
import discord
from discord.ext import commands
from timeit import default_timer as timer


from Steward.bot import StewardBot
from Steward.utils.discordUtils import is_owner
from constants import ADMIN_GUILDS

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(AdminCog(bot))


class AdminCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    # admin_commands = discord.SlashCommandGroup(
    #     "admin", "Bot Admin Commands", guild_ids=ADMIN_GUILDS
    # )

    @commands.group(hidden=True, invoke_without_command=True)
    @commands.check(is_owner)
    async def admin(self, ctx: discord.ApplicationContext):
        await ctx.send("Send a subcommand")

    @admin.command(hidden=True, name="eval")
    @commands.check(is_owner)
    async def admin_eval(self, ctx: discord.ApplicationContext, *, body: str):
        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "server": ctx.server,
        }

        def _cleanup_code(content):
            """Automatically removes code blocks from the code."""
            # remove ```py\n```
            if content.startswith("```") and content.endswith("```"):
                return "\n".join(content.split("\n")[1:-1])

            # remove `foo`
            return content.strip("` \n")

        env.update(globals())
        body = _cleanup_code(body)
        stdout = io.StringIO()

        to_compile = "async def func():\n{}".format(textwrap.indent(body, "  "))

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send("```py\n{}: {}\n```".format(e.__class__.__name__, e))

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await ctx.send("```py\n{}{}\n```".format(value, traceback.format_exc()))
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction("\u2705")
            except:
                pass

            if ret is None:
                if value:
                    await ctx.send("```py\n{}\n```".format(value))
            else:
                await ctx.send("```py\n{}{}\n```".format(value, ret))