import discord
import discord.ui as ui
from datetime import timezone
from typing import TYPE_CHECKING

from Steward.models.modals.auctionHouse import BidModal
from Steward.models.objects.exceptions import CharacterNotFound
from Steward.models.objects.player import Player
from Steward.models.views import StewardView
from Steward.models.modals import PromptModal, get_character_select_modal

if TYPE_CHECKING:
    from Steward.models.objects.auctionHouse import AuctionHouse, StockItem, Item
    from Steward.models.objects.character import Character


class AuctionHouseView(StewardView):
    """Main public view for the auction house showing all shelves and items"""
    
    def __init__(self, house: "AuctionHouse", owner=None):
        self.house = house
        
        container = ui.Container(
            ui.TextDisplay(f"## {self.house.name}"),
            ui.Separator()
        )

        if self.house.shelves:
            for shelf in self.house.shelves:
                if not shelf.items:
                    continue
                    
                # Shelf header
                container.add_item(
                    ui.TextDisplay(f"### {shelf.notes or 'Shelf'}")
                )

                # Group items by item_id to show quantity
                items_grouped = {}
                for stock_item in shelf.items:
                    if stock_item.item:
                        item_id = stock_item.item.id
                        if item_id not in items_grouped:
                            items_grouped[item_id] = {
                                'item': stock_item.item,
                                'stock_items': []
                            }
                        items_grouped[item_id]['stock_items'].append(stock_item)

                # Display each unique item with quantity
                for item_id, data in items_grouped.items():
                    item = data['item']
                    stock_items = data['stock_items']
                    qty_available = len(stock_items)
                    
                    min_bid = self.house.minimum_bid(item)

                    item_text = ui.TextDisplay(
                        f"- **{item.name}**: {qty_available} available - Min Bid: {min_bid:,.0f}"
                    )

                    item_button = ui.Button(
                        emoji="🪙",
                        custom_id=str(item_id)
                    )
                    item_button.callback = self._bid_button
                    
                    container.add_item(
                        ui.Section(
                            item_text,
                            accessory=item_button
                        )
                    )

        super().__init__(container, timeout=None)

    async def _bid_button(self, interaction: discord.Interaction):
        item_id = interaction.data["custom_id"]
        stock_item = next(
            (i for i in self.house.inventory if str(i.id) == item_id)
        )
        player = await Player.get_or_create(self.house._bot.db, interaction.user)
        item_detail_view = ItemDetailView(self.house, stock_item, player)

        await interaction.response.send_message(
            view=item_detail_view,
            ephemeral=True
        )

class ItemDetailView(StewardView):
    """Detailed view of a specific stock item with bidding options"""
    
    def __init__(self, house: "AuctionHouse", stock_item: "StockItem", player: "Player"):
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
        
        # Item header
        container.add_item(ui.TextDisplay(f"## {item.name}"))
        container.add_item(ui.Separator())
        
        # Item description
        if item.description:
            container.add_item(ui.TextDisplay(f"{item.description}"))
            container.add_item(ui.Separator())
        
        # Pricing info
        min_bid = house.minimum_bid(item)
        container.add_item(
            ui.TextDisplay(f"**Base Cost:** {item.cost:,.0f}\n**Minimum Bid:** {min_bid:,.0f}")
        )
        
        # Auction timing
        end_time = house.auction_end_at(stock_item)
        if end_time:
            timestamp = int(end_time.timestamp())
            container.add_item(
                ui.TextDisplay(
                    f"**Auction Ends:** <t:{timestamp}:F> (<t:{timestamp}:R>)"
                )
            )
        
        container.add_item(ui.Separator())
        
        # Current bids
        if stock_item.bids:
            bids_text = "**Current Bids:**\n"
            sorted_bids = sorted(stock_item.bids.items(), key=lambda x: x[1], reverse=True)
            for character, bid_amount in sorted_bids[:10]:  # Show top 10 bids
                bids_text += f"- {character.name}: {bid_amount:,.0f}\n"
            container.add_item(ui.TextDisplay(bids_text))
        else:
            container.add_item(ui.TextDisplay("*No bids yet*"))
        
        container.add_item(ui.Separator())
        
        # Buttons
        place_bid_button = ui.Button(
                label="Place Bid",
                style=discord.ButtonStyle.success,
                custom_id="place_bid_button"
            )
        place_bid_button.callback = self._place_bid_button

        exit_button = ui.Button(
                label="Exit",
                style=discord.ButtonStyle.danger,
                custom_id="exit_button"
            )
        exit_button.callback = self.timeout_callback

        button_row = ui.ActionRow(
            place_bid_button,
            exit_button
        )
        container.add_item(button_row)
        
        super().__init__(container, timeout=300)
        

    async def _place_bid_button(self, interaction: discord.Interaction):
        """Show modal to place a bid"""
        item = self.stock_item.item
        min_bid = self.house.minimum_bid(item)
        
        # Calculate minimum bid (must beat current highest)
        if self.stock_item.bids:
            min_bid = max(min_bid, max(self.stock_item.bids.values()) + 1)

        if not self.player.active_characters:
            raise CharacterNotFound(self.player)

        if len(self.player.active_characters) == 1:
            self.character = self.player.primary_character
        else:
            self.character = await get_character_select_modal(
                interaction,
                self.player.active_characters,   
            )

        if not self.character:
            await interaction.response.send_message(
                f"No character identified",
                ephemeral=True
            )
        
        modal = BidModal(self.character, self.house, self.stock_item, min_bid)
        await interaction.response.send_modal(modal)
        
        # Wait for modal completion
        await modal.wait()
        
        # Refresh the view to show updated bids
        if modal.bid_placed:
            # Reload the stock item with updated bids
            from Steward.models.objects.auctionHouse import StockItem
            updated_stock = await StockItem.fetch(
                self.house._bot.db,
                self.stock_item.id,
                load_bids=True
            )
            if updated_stock:
                self.stock_item = updated_stock
                
            # Update the view
            updated_view = AuctionHouseView(self.house, self.user)
            await interaction.edit_original_response(view=updated_view)
