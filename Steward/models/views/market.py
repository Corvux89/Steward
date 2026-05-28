import discord
import discord.ui as ui
from typing import TYPE_CHECKING
import uuid

from Steward.models.objects.exceptions import CharacterNotFound
from Steward.models.objects.player import Player
from Steward.models.views import StewardView
from Steward.models.modals import PromptModal

if TYPE_CHECKING:
    from Steward.models.objects.market import Shop, StockItem, Item


class ShopView(StewardView):
    """Persistent public-facing view for a shop, pinned in the shop channel."""

    CUSTOM_ID_PREFIX = "shop"

    async def interaction_check(self, _: discord.Interaction) -> bool:
        return True

    @classmethod
    def _make_custom_id(cls, action: str, *parts: object) -> str:
        base = f"{cls.CUSTOM_ID_PREFIX}:{action}"
        if parts:
            base += ":" + ":".join(str(p) for p in parts)
        return base

    @classmethod
    def _parse_custom_id(cls, value: str):
        if not value:
            return None, []
        parts = value.split(":")
        if len(parts) < 2 or parts[0] != cls.CUSTOM_ID_PREFIX:
            return None, []
        return parts[1], parts[2:]

    def __init__(self, shop: "Shop", owner=None):
        self.shop = shop

        container = ui.Container(
            ui.TextDisplay(f"## {self.shop.name}"),
        )

        if self.shop.description:
            container.add_item(ui.TextDisplay(self.shop.description))

        info_parts = [f"Ticket cost: **{self.shop.ticket_cost:,.0f}**", f"Max per item: **{self.shop.max_tickets}**"]
        if self.shop.raffle_duration:
            info_parts.append(f"Raffle duration: **{self.shop.raffle_duration:.0f}h**")
        container.add_item(ui.TextDisplay("-# " + " | ".join(info_parts)))
        container.add_item(ui.Separator())

        has_stock = False
        if self.shop.shelves:
            for shelf in self.shop.shelves:
                if not shelf.items:
                    continue

                has_stock = True

                if shelf.description:
                    container.add_item(ui.TextDisplay(f"### {shelf.description}"))

                for stock in shelf.items:
                    if not stock.item:
                        continue

                    ticket_count = sum(t.quantity for t in stock.tickets)
                    end_time = self.shop.raffle_end_at(stock)
                    time_str = f"<t:{int(end_time.timestamp())}:R>" if end_time else "`Always open`"

                    item_text = ui.TextDisplay(
                        f"**{stock.item.name}** — {ticket_count} ticket(s) | Ends {time_str}"
                    )

                    buy_button = ui.Button(
                        emoji="🎟️",
                        label="Buy Ticket",
                        style=discord.ButtonStyle.primary,
                        custom_id=self._make_custom_id("buy", stock.id),
                    )
                    buy_button.callback = self._buy_ticket_button

                    container.add_item(ui.Section(item_text, accessory=buy_button))

        if not has_stock:
            container.add_item(ui.TextDisplay("*No items currently in stock.*"))

        super().__init__(container, timeout=None)

    async def _buy_ticket_button(self, interaction: discord.Interaction):
        action, parts = self._parse_custom_id(interaction.data.get("custom_id", ""))
        if action != "buy" or not parts:
            await interaction.response.send_message("Invalid action.", ephemeral=True)
            return

        try:
            stock_id = uuid.UUID(parts[0])
        except ValueError:
            await interaction.response.send_message("Invalid item.", ephemeral=True)
            return

        stock = next((s for s in self.shop.stock if s.id == stock_id), None)
        if not stock:
            await interaction.response.send_message("That item is no longer available.", ephemeral=True)
            return

        player = await Player.get_or_create(self.shop._bot.db, interaction.user)
        view = TicketPurchaseView(self.shop, stock, player)
        await interaction.response.send_message(view=view, ephemeral=True)


class TicketPurchaseView(StewardView):
    """Ephemeral detail view shown per-user to purchase raffle tickets."""

    __copy_attrs__ = ["shop", "stock", "player"]

    def __init__(self, shop: "Shop", stock: "StockItem", player: "Player"):
        self.shop = shop
        self.stock = stock
        self.player = player
        self.owner = player

        item = stock.item
        container = ui.Container()

        if not item:
            container.add_item(ui.TextDisplay("Item data is unavailable."))
            super().__init__(container, timeout=300)
            return

        container.add_item(ui.TextDisplay(f"## {item.name}"))
        container.add_item(ui.Separator())

        if item.description:
            container.add_item(ui.TextDisplay(item.description))
            container.add_item(ui.Separator())

        existing = next((t for t in stock.tickets if t.character_id and
                         any(c.id == t.character_id for c in player.active_characters)), None)
        held = existing.quantity if existing else 0
        remaining = shop.max_tickets - held

        end_time = shop.raffle_end_at(stock)
        time_str = f"<t:{int(end_time.timestamp())}:R>" if end_time else "`Always open`"
        ticket_count = sum(t.quantity for t in stock.tickets)

        container.add_item(ui.TextDisplay(
            f"**Ticket cost:** {shop.ticket_cost:,.0f}\n"
            f"**Your tickets:** {held} / {shop.max_tickets}\n"
            f"**Total tickets sold:** {ticket_count}\n"
            f"**Raffle ends:** {time_str}"
        ))

        container.add_item(ui.Separator())

        if remaining > 0:
            buy_button = ui.Button(
                label=f"Buy Ticket(s)",
                style=discord.ButtonStyle.success,
                custom_id="ticket_buy",
            )
            buy_button.callback = self._buy_callback
            container.add_item(ui.ActionRow(buy_button))
        else:
            container.add_item(ui.TextDisplay("*You've purchased the maximum tickets for this item.*"))

        super().__init__(container, timeout=300)

    async def _buy_callback(self, interaction: discord.Interaction):
        # Reload fresh stock to avoid stale data
        from Steward.models.objects.market import StockItem as StockModel, Shop as ShopModel

        fresh_shop = await ShopModel.fetch_by_id(self.shop._bot, self.shop.id, load_related=True)
        if not fresh_shop:
            await interaction.response.send_message("Shop no longer available.", ephemeral=True)
            return

        fresh_stock = next((s for s in fresh_shop.stock if s.id == self.stock.id), None)
        if not fresh_stock:
            await interaction.response.send_message("That item is no longer in stock.", ephemeral=True)
            return

        existing = next(
            (t for t in fresh_stock.tickets
             if any(c.id == t.character_id for c in self.player.active_characters)),
            None
        )
        max_available = fresh_shop.max_tickets - (existing.quantity if existing else 0)

        if max_available <= 0:
            await interaction.response.send_message(
                "You've already purchased the maximum tickets for this item.", ephemeral=True
            )
            return

        # Pick character
        if not self.player.active_characters:
            raise CharacterNotFound(self.player)

        if len(self.player.active_characters) == 1:
            character = self.player.primary_character
        else:
            # Ask character
            char_modal = PromptModal(
                label="Character",
                current_value=None,
                title="Choose a Character",
                items=[c.name for c in self.player.active_characters],
                required=True,
            )
            await self.prompt_modal(char_modal, interaction)
            if not char_modal.value:
                return
            character = next(
                (c for c in self.player.active_characters if c.name == char_modal.value), None
            )
            if not character:
                await interaction.followup.send("Character not found.", ephemeral=True)
                return

        # Ask quantity if they can buy more than 1
        quantity = 1
        if max_available > 1:
            qty_modal = PromptModal(
                label="Quantity",
                current_value="1",
                title="How many tickets?",
                placeholder=f"1–{max_available}",
                integer=True,
                required=True,
            )
            if len(self.player.active_characters) == 1:
                await self.prompt_modal(qty_modal, interaction)
            else:
                await interaction.followup.send_modal(qty_modal)
                await qty_modal.wait()

            if qty_modal.value is None:
                return
            try:
                quantity = int(qty_modal.value)
            except (TypeError, ValueError):
                await interaction.followup.send("Invalid quantity.", ephemeral=True)
                return
            if quantity < 1 or quantity > max_available:
                await interaction.followup.send(
                    f"Please enter a number between 1 and {max_available}.", ephemeral=True
                )
                return

        success, message = await fresh_shop.buy_ticket(fresh_stock, character, quantity)

        if success:
            await fresh_shop.refresh_view()

        try:
            await interaction.followup.send(message, ephemeral=True)
        except Exception:
            pass
