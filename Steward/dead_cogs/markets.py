import logging
import random
from datetime import timedelta

import discord
import discord.ui as ui
from discord.ext import commands, tasks

from Steward.bot import StewardApplicationContext, StewardBot
from Steward.models.objects.auctionhouse import InventoryItem, Market
from Steward.models.objects.player import Player
from Steward.utils.discordUtils import is_admin

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(MarketCog(bot))


class BidModal(ui.Modal):
    def __init__(self, cog: "MarketCog", market_id, inventory_id, minimum_bid: int):
        self.cog = cog
        self.market_id = market_id
        self.inventory_id = inventory_id
        self.amount = ui.InputText(label=f"Bid Amount (min {minimum_bid})", required=True)
        super().__init__(self.amount, title="Place Bid")

    async def callback(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("Bid must be a whole number.", ephemeral=True)

        await self.cog.place_bid(interaction, self.market_id, self.inventory_id, amount)


class MarketInventorySelect(ui.Select):
    def __init__(self, cog: "MarketCog", market: Market):
        self.cog = cog
        self.market = market

        options = []
        items_by_id = {str(item.id): item for item in market.items}

        for inv in market.inventory[:25]:
            item = items_by_id.get(str(inv.item_id))
            if not item:
                continue

            if market.type.name == "auction":
                detail = f"Min Bid: {market.minimum_bid(item):,.0f}"
            else:
                detail = f"Price: {item.cost:,.0f}"

            options.append(
                discord.SelectOption(
                    label=item.name[:100],
                    description=detail[:100],
                    value=str(inv.id)
                )
            )

        super().__init__(
            placeholder="Select an item to bid/buy",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"market_select:{market.id}"
        )

    async def callback(self, interaction: discord.Interaction):
        inv_id = self.values[0]
        market = await Market.fetch_by_id(self.cog.bot, self.market.id)

        if not market:
            return await interaction.response.send_message("Market not found.", ephemeral=True)

        inventory_item = next((i for i in market.inventory if str(i.id) == inv_id), None)
        if not inventory_item:
            return await interaction.response.send_message("That listing is no longer available.", ephemeral=True)

        item = next((itm for itm in market.items if itm.id == inventory_item.item_id), None)
        if not item:
            return await interaction.response.send_message("That item is no longer available.", ephemeral=True)

        if market.type.name == "auction":
            minimum_bid = market.minimum_bid(item)
            if inventory_item.bids:
                minimum_bid = max(minimum_bid, max(inventory_item.bids.values()) + 1)

            modal = BidModal(self.cog, market.id, inventory_item.id, int(minimum_bid))
            return await interaction.response.send_modal(modal)

        await self.cog.buy_item(interaction, market.id, inventory_item.id)


class MarketInventoryView(ui.View):
    def __init__(self, cog: "MarketCog", market: Market):
        super().__init__(timeout=None)
        self.cog = cog
        self.market = market

        if market.inventory:
            self.add_item(MarketInventorySelect(cog, market))


class MarketCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot: StewardBot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    market_admin_commands = discord.SlashCommandGroup(
        "market_admin",
        "Market administration commands",
        contexts=[discord.InteractionContextType.guild]
    )

    @market_admin_commands.command(name="refresh", description="Refresh market displays")
    @commands.check(is_admin)
    async def refresh_markets(self, ctx: "StewardApplicationContext"):
        await ctx.defer()
        await self.refresh_guild_markets(ctx.guild.id)
        await ctx.respond("Markets refreshed.")

    @market_admin_commands.command(name="reroll", description="Force reroll all markets")
    @commands.check(is_admin)
    async def reroll_markets(self, ctx: "StewardApplicationContext"):
        await ctx.defer()
        markets = await Market.fetch_all(self.bot, ctx.guild.id)
        for market in markets:
            await self.reroll_market(market)
        await ctx.respond("Markets rerolled.")

    @commands.Cog.listener()
    async def on_db_connected(self):
        self.market_loop.start()
        await self.refresh_all_markets()

    def cog_unload(self):
        self.market_loop.cancel()

    @tasks.loop(minutes=1)
    async def market_loop(self):
        await self.refresh_all_markets()
        await self.process_market_timers()

    @market_loop.before_loop
    async def before_market_loop(self):
        await self.bot.wait_until_ready()

    def render_market_content(self, market: Market) -> str:
        now = discord.utils.utcnow()
        lines = [f"## {market.name}"]
        lines.append(f"Type: {market.type.value}")

        reroll_at = market.next_reroll_at()
        if reroll_at:
            lines.append(f"Next reroll: <t:{int(reroll_at.timestamp())}:R>")

        if not market.inventory:
            lines.append("\nNo inventory listed right now.")
            return "\n".join(lines)

        items_by_id = {item.id: item for item in market.items}
        shelves_by_id = {shelf.id: shelf for shelf in market.shelves}

        lines.append("\n### Inventory")
        for inv in market.inventory:
            item = items_by_id.get(inv.item_id)
            shelf = shelves_by_id.get(inv.shelf_id)
            if not item:
                continue

            shelf_label = f"Shelf {shelf.priority}" if shelf else "Shelf"

            if market.type.name == "auction":
                highest = max(inv.bids.values()) if inv.bids else None
                ending = market.auction_end_at(inv)
                lines.append(
                    f"- {shelf_label}: **{item.name}** | min {market.minimum_bid(item):,.0f} | "
                    f"high {highest:,.0f}" if highest else f"- {shelf_label}: **{item.name}** | min {market.minimum_bid(item):,.0f}"
                )
                if ending:
                    lines[-1] += f" | ends <t:{int(ending.timestamp())}:R>"
            else:
                lines.append(f"- {shelf_label}: **{item.name}** | price {item.cost:,.0f}")

        lines.append("\n-# Use the selector below to bid or buy.")
        return "\n".join(lines)

    async def refresh_market_message(self, market: Market):
        market = await Market.fetch_by_id(self.bot, market.id)
        if not market:
            return

        channel = market.channel
        if not isinstance(channel, discord.TextChannel):
            return

        content = self.render_market_content(market)
        view = MarketInventoryView(self, market)

        message = None
        if market.message_id:
            try:
                message = await channel.fetch_message(market.message_id)
            except Exception:
                message = None

        if not message:
            message = await channel.send(content=content, view=view)
            market.message_id = message.id
            await market.upsert()

        if not message.pinned:
            try:
                await message.pin()
            except Exception:
                pass

        await message.edit(content=content, view=view)

    async def refresh_guild_markets(self, guild_id: int):
        markets = await Market.fetch_all(self.bot, guild_id)
        for market in markets:
            await self.refresh_market_message(market)

    async def refresh_all_markets(self):
        for guild in self.bot.guilds:
            await self.refresh_guild_markets(guild.id)

    async def process_market_timers(self):
        now = discord.utils.utcnow()

        for guild in self.bot.guilds:
            markets = await Market.fetch_all(self.bot, guild.id)
            for market in markets:
                if market.type.name == "auction":
                    for inv in list(market.inventory):
                        ending = market.auction_end_at(inv)
                        if ending and now >= ending:
                            await market.finalize_item(inv, "Auction ended")

                reroll_at = market.next_reroll_at()
                if reroll_at and now >= reroll_at:
                    await self.reroll_market(market)

                if not market.inventory and market.reroll_interval:
                    await self.reroll_market(market)

    async def place_bid(self, interaction: discord.Interaction, market_id, inventory_id, amount: int):
        market = await Market.fetch_by_id(self.bot, market_id)
        if not market:
            return await interaction.response.send_message("Market not found.", ephemeral=True)

        if market.type.name != "auction":
            return await interaction.response.send_message("Bidding is only available for auction markets.", ephemeral=True)

        inventory_item = next((inv for inv in market.inventory if inv.id == inventory_id), None)
        if not inventory_item:
            return await interaction.response.send_message("That listing is no longer available.", ephemeral=True)

        item = next((itm for itm in market.items if itm.id == inventory_item.item_id), None)
        if not item:
            return await interaction.response.send_message("That listing is no longer available.", ephemeral=True)

        guild = market.guild
        member = guild.get_member(interaction.user.id) if guild else None
        if not member:
            return await interaction.response.send_message("Could not resolve your member profile.", ephemeral=True)

        player = await Player.get_or_create(self.bot.db, member)
        if not player.active_characters:
            return await interaction.response.send_message("You need an active character to bid.", ephemeral=True)

        character = player.primary_character

        minimum = market.minimum_bid(item)
        if inventory_item.bids:
            minimum = max(minimum, max(inventory_item.bids.values()) + 1)

        if amount < minimum:
            return await interaction.response.send_message(f"Bid must be at least {int(minimum):,}.", ephemeral=True)

        if character.currency < amount:
            return await interaction.response.send_message("Your primary character cannot cover that bid.", ephemeral=True)

        bids_by_id = {str(char.id): int(bid) for char, bid in (inventory_item.bids or {}).items()}
        bids_by_id[str(character.id)] = int(amount)

        await inventory_item.upsert_bids(bids_by_id)
        await self.refresh_market_message(market)

        await interaction.response.send_message(f"Bid placed for **{item.name}** at {amount:,}.", ephemeral=True)

    async def buy_item(self, interaction: discord.Interaction, market_id, inventory_id):
        market = await Market.fetch_by_id(self.bot, market_id)
        if not market:
            return await interaction.response.send_message("Market not found.", ephemeral=True)

        if market.type.name != "shop":
            return await interaction.response.send_message("Buying is only available for shop markets.", ephemeral=True)

        inventory_item = next((inv for inv in market.inventory if inv.id == inventory_id), None)
        if not inventory_item:
            return await interaction.response.send_message("That listing is no longer available.", ephemeral=True)

        item = next((itm for itm in market.items if itm.id == inventory_item.item_id), None)
        if not item:
            return await interaction.response.send_message("That listing is no longer available.", ephemeral=True)

        guild = market.guild
        member = guild.get_member(interaction.user.id) if guild else None
        if not member:
            return await interaction.response.send_message("Could not resolve your member profile.", ephemeral=True)

        player = await Player.get_or_create(self.bot.db, member)
        if not player.active_characters:
            return await interaction.response.send_message("You need an active character to buy.", ephemeral=True)

        character = player.primary_character

        if character.currency < item.cost:
            return await interaction.response.send_message("Your primary character cannot afford this item.", ephemeral=True)

        character.currency -= item.cost
        await character.upsert()
        await inventory_item.delete()
        await self.refresh_market_message(market)

        try:
            await market.channel.send(f"{member.mention} bought **{item.name}** for {item.cost:,.0f}.")
        except Exception:
            pass

        await interaction.response.send_message(f"Purchased **{item.name}** for {item.cost:,.0f}.", ephemeral=True)

    async def reroll_market(self, market: Market):
        market = await Market.fetch_by_id(self.bot, market.id)
        if not market:
            return

        for inv in list(market.inventory):
            if market.type.name == "auction":
                await market.finalize_item(inv, "Inventory rerolled")
            else:
                await inv.delete()

        market = await Market.fetch_by_id(self.bot, market.id)
        if not market:
            return

        if not market.shelves or not market.items:
            await self.refresh_market_message(market)
            return

        shelves = sorted(market.shelves, key=lambda shelf: shelf.priority)
        remaining_slots = {shelf.id: max(0, int(shelf.max_qty or 0)) for shelf in shelves}
        item_counts = {item.id: 0 for item in market.items}
        placements = []

        for item in market.items:
            min_qty = max(0, int(item.min_qty or 0))
            for _ in range(min_qty):
                eligible_shelves = [shelf for shelf in shelves if remaining_slots[shelf.id] > 0]
                if not eligible_shelves:
                    break

                shelf = random.choice(eligible_shelves)
                placements.append((item.id, shelf.id))
                remaining_slots[shelf.id] -= 1
                item_counts[item.id] += 1

        for shelf in shelves:
            while remaining_slots[shelf.id] > 0:
                eligible_items = [
                    item for item in market.items
                    if item.max_qty is None or item_counts[item.id] < int(item.max_qty)
                ]

                if not eligible_items:
                    break

                item = random.choice(eligible_items)
                placements.append((item.id, shelf.id))
                remaining_slots[shelf.id] -= 1
                item_counts[item.id] += 1

        now = discord.utils.utcnow()
        for item_id, shelf_id in placements:
            inv = InventoryItem(self.bot.db, item_id=item_id, shelf_id=shelf_id, auction_start=now)
            await inv.upsert()

        refreshed_market = await Market.fetch_by_id(self.bot, market.id)
        await self.refresh_market_message(refreshed_market)

        try:
            await refreshed_market.channel.send(f"{refreshed_market.name} inventory rerolled.")
        except Exception:
            pass
