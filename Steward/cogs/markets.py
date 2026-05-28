import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from Steward.bot import StewardBot, StewardApplicationContext
from Steward.models.objects.market import Shop
from Steward.utils.discordUtils import is_admin

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(MarketCog(bot))


class MarketCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot: StewardBot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    @commands.Cog.listener()
    async def on_db_connected(self):
        shops = await Shop.fetch_all(self.bot)

        for shop in shops:
            await shop.refresh_view()

        self.market_loop.start()

    def cog_unload(self):
        self.market_loop.cancel()

    @tasks.loop(minutes=1)
    async def market_loop(self):
        shops = await Shop.fetch_all(self.bot)
        now = datetime.now(timezone.utc)

        for shop in shops:
            for stock in list(shop.stock):
                end = shop.raffle_end_at(stock)
                if end and now >= end:
                    await shop.finalize_raffle(stock, "Raffle Ended")

    @market_loop.before_loop
    async def before_market_loop(self):
        await self.bot.wait_until_ready()

    market_commands = discord.SlashCommandGroup(
        "market",
        "Market administration commands",
        contexts=[discord.InteractionContextType.guild]
    )

    @market_commands.command(
        name="reroll",
        description="Finalize all active raffles and restock the shop with fresh inventory"
    )
    @commands.check(is_admin)
    async def reroll(
        self,
        ctx: "StewardApplicationContext",
        shop_name: discord.Option(
            str,
            description="Shop name or ID",
            required=True,
            autocomplete=discord.utils.basic_autocomplete(
                lambda ctx: _shop_autocomplete(ctx)
            )
        )
    ):
        await ctx.defer()

        shops = await Shop.fetch_by_guild(self.bot, ctx.guild.id, load_related=False)
        shop = _resolve_shop(shops, shop_name)

        if not shop:
            await ctx.respond(f"No shop found matching `{shop_name}`.", ephemeral=True)
            return

        shop = await Shop.fetch_by_id(self.bot, shop.id, load_related=True)
        await shop.reroll_inventory()
        await ctx.respond(f"Inventory for **{shop.name}** has been rerolled!", ephemeral=True)


def _resolve_shop(shops: list["Shop"], value: str) -> "Shop | None":
    normalized = value.strip()
    try:
        import uuid
        incoming_id = uuid.UUID(normalized)
        found = next((s for s in shops if s.id == incoming_id), None)
        if found:
            return found
    except ValueError:
        pass
    return next((s for s in shops if s.name.lower() == normalized.lower()), None)


async def _shop_autocomplete(ctx: discord.AutocompleteContext) -> list[str]:
    try:
        shops = await Shop.fetch_by_guild(ctx.bot, ctx.interaction.guild.id, load_related=False)
        user_input = ctx.value.lower() if ctx.value else ""
        return [s.name for s in shops if user_input in s.name.lower()][:25]
    except Exception:
        return []
