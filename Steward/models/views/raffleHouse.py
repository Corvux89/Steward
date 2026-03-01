import uuid
from typing import TYPE_CHECKING

import discord
import discord.ui as ui

from Steward.models.modals.raffleHouse import BuyTicketModal
from Steward.models.objects.exceptions import CharacterNotFound
from Steward.models.objects.player import Player
from Steward.models.views import StewardView
from constants import APPROVAL_EMOJI

if TYPE_CHECKING:
    from Steward.models.objects.raffleHouse import Raffle, StockItem


class RaffleView(StewardView):
    CUSTOM_ID_PREFIX = "rf"

    async def interaction_check(self, _: discord.Interaction):
        return True

    @classmethod
    def _make_custom_id(cls, action: str, *parts: object) -> str:
        if parts:
            return f"{cls.CUSTOM_ID_PREFIX}:{action}:" + ":".join(str(part) for part in parts)
        return f"{cls.CUSTOM_ID_PREFIX}:{action}"

    @classmethod
    def _parse_custom_id(cls, value: str):
        if not value:
            return None, []
        parts = value.split(":")
        if len(parts) < 2 or parts[0] != cls.CUSTOM_ID_PREFIX:
            return None, []
        return parts[1], parts[2:]

    def __init__(self, house: "Raffle", owner=None):
        self.house = house

        container = ui.Container(
            ui.TextDisplay(f"## {self.house.name}"),
            ui.TextDisplay("-# Raffle workflow active"),
            ui.Separator()
        )

        for shelf in self.house.shelves:
            if not shelf.items:
                continue

            container.add_item(ui.TextDisplay(f"### {shelf.notes or 'Shelf'}"))

            items_grouped = {}
            for stock_item in shelf.items:
                if not stock_item.item:
                    continue
                item_id = stock_item.item.id
                if item_id not in items_grouped:
                    items_grouped[item_id] = {
                        "item": stock_item.item,
                        "stock_items": []
                    }
                items_grouped[item_id]["stock_items"].append(stock_item)

            for item_id, data in items_grouped.items():
                item = data["item"]
                stock_items = data["stock_items"]
                qty_available = len(stock_items)
                ticket_cost = self.house.ticket_cost(item)

                sold = sum(self.house.tickets_sold(stock) for stock in stock_items)
                remaining_text = "∞"
                if self.house.max_tickets:
                    remaining = sum(
                        self.house.tickets_remaining(stock) or 0
                        for stock in stock_items
                    )
                    remaining_text = str(remaining)

                item_text = ui.TextDisplay(
                    f"- **{item.name}**: {qty_available} available | Ticket: {ticket_cost:,.0f} | Sold: {sold} | Remaining: {remaining_text}"
                )

                item_button = ui.Button(
                    emoji="🎟️",
                    custom_id=self._make_custom_id("details", shelf.id, item.id)
                )
                item_button.callback = self._details_button

                container.add_item(ui.Section(item_text, accessory=item_button))

        super().__init__(container, timeout=None)

    async def _details_button(self, interaction: discord.Interaction):
        action, parts = self._parse_custom_id(interaction.data.get("custom_id"))
        if action != "details" or len(parts) < 2:
            await interaction.response.send_message("Invalid action.", ephemeral=True)
            return

        try:
            shelf_id = uuid.UUID(parts[0])
            item_id = uuid.UUID(parts[1])
        except ValueError:
            await interaction.response.send_message("Invalid item.", ephemeral=True)
            return

        item_stock_items = [
            stock_item
            for stock_item in self.house.inventory
            if stock_item.item_id == item_id and stock_item.shelf_id == shelf_id
        ]

        if not item_stock_items:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return

        player = await Player.get_or_create(self.house._bot.db, interaction.user)

        if len(item_stock_items) == 1:
            item_detail_view = ItemDetailView(self.house, item_stock_items[0], player)
            await interaction.response.send_message(view=item_detail_view, ephemeral=True)
            return

        select_view = StockItemSelectView(self.house, item_stock_items, player)
        await interaction.response.send_message(view=select_view, ephemeral=True)


class ItemDetailView(StewardView):
    __copy_attrs__ = ["house", "stock_item", "player"]

    def __init__(self, house: "Raffle", stock_item: "StockItem", player: "Player"):
        self.owner = player
        self.house = house
        self.stock_item = stock_item
        self.player = player

        container = ui.Container()

        item = stock_item.item
        if not item:
            container.add_item(ui.TextDisplay("Item data not available."))
            super().__init__(container, timeout=300)
            return

        container.add_item(ui.TextDisplay(f"## {item.name}"))
        container.add_item(ui.Separator())

        if item.description:
            container.add_item(ui.TextDisplay(item.description))
            container.add_item(ui.Separator())

        ticket_cost = house.ticket_cost(item)
        sold = house.tickets_sold(stock_item)
        remaining = house.tickets_remaining(stock_item)
        remaining_text = "∞" if remaining is None else f"{remaining:,}"

        my_tickets = 0
        if stock_item.tickets:
            for character, qty in stock_item.tickets.items():
                if character.player_id == player.id:
                    my_tickets += int(qty)

        container.add_item(
            ui.TextDisplay(
                f"**Item Cost:** {item.cost:,.0f}\n"
                f"**Ticket Cost:** {ticket_cost:,.0f}\n"
                f"**Tickets Sold:** {sold:,}\n"
                f"**Tickets Remaining:** {remaining_text}\n"
                f"**Your Tickets:** {my_tickets:,}"
            )
        )

        end_time = house.raffle_end_at(stock_item)
        if end_time:
            timestamp = int(end_time.timestamp())
            container.add_item(ui.Separator())
            container.add_item(ui.TextDisplay(f"**Raffle Ends:** <t:{timestamp}:R>"))

        container.add_item(ui.Separator())
        buy_button = ui.Button(
            label="Buy Tickets",
            style=discord.ButtonStyle.success,
            custom_id=RaffleView._make_custom_id("buy_ticket")
        )
        buy_button.callback = self._buy_ticket_button
        container.add_item(ui.ActionRow(buy_button))

        super().__init__(container, timeout=300)

    async def _buy_ticket_button(self, interaction: discord.Interaction):
        if not self.player.active_characters:
            raise CharacterNotFound(self.player)

        existing_character_ids = {
            character.id
            for character in (self.stock_item.tickets or {}).keys()
        }

        available_characters = [
            character for character in self.player.active_characters
            if character.id not in existing_character_ids
        ]

        if not available_characters:
            await interaction.response.send_message(
                "You already have a ticket entry for this item.",
                ephemeral=True
            )
            return

        remaining = self.house.tickets_remaining(self.stock_item)
        max_qty = 1 if remaining is None else max(0, min(remaining, 25))

        if max_qty <= 0:
            await interaction.response.send_message(
                "This raffle has reached max tickets.",
                ephemeral=True
            )
            return

        characters = None
        if len(available_characters) == 1:
            character = available_characters[0]
        else:
            character = None
            characters = list(available_characters)

        modal = BuyTicketModal(character, self.house, self.stock_item, max_qty, characters=characters)
        await self.prompt_modal(modal, interaction)

        if modal.tickets_purchased:
            from Steward.models.objects.raffleHouse import StockItem
            updated_stock = await StockItem.fetch(self.house._bot.db, self.stock_item.id)
            if updated_stock:
                self.stock_item = updated_stock

            await self.house.refresh_view()
            await self.refresh_content(interaction)


class StockItemSelectView(StewardView):
    def __init__(self, house: "Raffle", stock_items: list["StockItem"], player: "Player"):
        self.house = house
        self.stock_items = stock_items
        self.player = player
        self.owner = self.player

        container = ui.Container(
            ui.TextDisplay("**Select which item to buy tickets for:**"),
            ui.Separator()
        )

        for idx, stock_item in enumerate(stock_items, 1):
            sold = house.tickets_sold(stock_item)
            remaining = house.tickets_remaining(stock_item)
            remaining_text = "∞" if remaining is None else str(remaining)

            info_text = (
                f"**{stock_item.item.name} {idx}**\n"
                f"Tickets Sold: {sold}\n"
                f"Remaining: {remaining_text}"
            )

            end_time = house.raffle_end_at(stock_item)
            if end_time:
                timestamp = int(end_time.timestamp())
                info_text += f"\nEnds: <t:{timestamp}:R>"

            select_button = ui.Button(
                emoji=APPROVAL_EMOJI[0],
                style=discord.ButtonStyle.secondary,
                custom_id=RaffleView._make_custom_id("select_stock", stock_item.id)
            )
            select_button.callback = self._make_select_callback(stock_item)

            container.add_item(ui.Section(ui.TextDisplay(info_text), accessory=select_button))

            if idx < len(stock_items):
                container.add_item(ui.Separator())

        super().__init__(container, timeout=60)

    def _make_select_callback(self, stock_item: "StockItem"):
        async def callback(interaction: discord.Interaction):
            item_detail_view = ItemDetailView(self.house, stock_item, self.player)
            await interaction.response.edit_message(view=item_detail_view)
        return callback


AuctionHouseView = RaffleView
