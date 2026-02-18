import discord
import discord.ui as ui
from datetime import timezone
from typing import TYPE_CHECKING

from Steward.models.views import StewardView
from Steward.models.modals import PromptModal

if TYPE_CHECKING:
    from Steward.models.objects.auctionHouse import AuctionHouse, StockItem, Item
    from Steward.models.objects.character import Character


class AuctionHouseView(StewardView):
    """Main public view for the auction house showing all shelves and items"""
    
    def __init__(self, market: "AuctionHouse", owner=None):
        self.market = market
        
        container = ui.Container(
            ui.TextDisplay(f"## {self.market.name}"),
            ui.Separator()
        )

        if self.market.shelves:
            for shelf in self.market.shelves:
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
                    
                    min_bid = self.market.minimum_bid(item)

                    item_text = ui.TextDisplay(
                        f"- **{item.name}**: {qty_available} available - Min Bid: {min_bid:,.0f}"
                    )

                    item_button = ui.Button(
                        emoji="🪙"
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
        from discord
        item_id = interaction.data["custom_id"]
        stock_item = next(
            (i for i in self.market.inventory if str(i.id) == item_id)
        )
        item_detail_view = ItemDetailView(self.market, stock_item, interaction.user)
        
        await interaction.response.send_message(
            view=item_detail_view,
            ephemeral=True
        )


class ItemSelectionView(StewardView):
    """Private ephemeral view for a specific user to select which item to bid on"""
    
    def __init__(self, market: "AuctionHouse", user: discord.User):
        self.market = market
        self.user = user
        
        container = ui.Container(
            ui.TextDisplay(f"## Select Item to Bid On"),
            ui.Separator()
        )

        # Create select menu options for all available items
        options = []
        self.stock_items_map = {}
        
        for stock_item in self.market.inventory:
            if stock_item.item:
                option_value = str(stock_item.id)
                self.stock_items_map[option_value] = stock_item
                
                # Get auction end time
                end_time = self.market.auction_end_at(stock_item)
                time_str = f"Ends <t:{int(end_time.timestamp())}:R>" if end_time else "No end time"
                
                # Get current highest bid if any
                bid_info = ""
                if stock_item.bids:
                    highest_bid = max(stock_item.bids.values())
                    bid_info = f" - Current: {highest_bid:,.0f}"
                
                min_bid = self.market.minimum_bid(stock_item.item)
                
                options.append(
                    discord.SelectOption(
                        label=stock_item.item.name[:100],
                        description=f"Min: {min_bid:,.0f}{bid_info} | {time_str}"[:100],
                        value=option_value
                    )
                )
        
        # Limit to 25 options (Discord limit)
        if options:
            container.add_item(
                ui.Select(
                    placeholder="Choose an item...",
                    options=options[:25],
                    custom_id="item_select"
                )
            )
        else:
            container.add_item(
                ui.TextDisplay("No items currently available for bidding.")
            )

        super().__init__(container, timeout=300)
        self.owner = user

    @ui.select.callback("item_select")
    async def on_item_select(self, select: ui.Select, interaction: discord.Interaction):
        """Show detailed view for the selected item"""
        selected_id = select.values[0]
        stock_item = self.stock_items_map.get(selected_id)
        
        if not stock_item:
            return await interaction.response.send_message(
                "Item not found.",
                ephemeral=True
            )
        
        # Show item detail view
        detail_view = ItemDetailView(self.market, stock_item, interaction.user)
        await interaction.response.edit_message(view=detail_view)


class ItemDetailView(StewardView):
    """Detailed view of a specific stock item with bidding options"""
    
    def __init__(self, market: "AuctionHouse", stock_item: "StockItem", user: discord.User):
        self.market = market
        self.stock_item = stock_item
        self.user = user
        
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
        min_bid = market.minimum_bid(item)
        container.add_item(
            ui.TextDisplay(f"**Base Cost:** {item.cost:,.0f}\n**Minimum Bid:** {min_bid:,.0f}")
        )
        
        # Auction timing
        end_time = market.auction_end_at(stock_item)
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
        button_row = ui.ActionRow(
            ui.Button(
                label="Place Bid",
                style=discord.ButtonStyle.success,
                custom_id="place_bid_button"
            ),
            ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id="back_button"
            )
        )
        container.add_item(button_row)
        
        super().__init__(container, timeout=300)
        self.owner = user

    @ui.button.callback("place_bid_button")
    async def on_place_bid(self, button: ui.Button, interaction: discord.Interaction):
        """Show modal to place a bid"""
        item = self.stock_item.item
        min_bid = self.market.minimum_bid(item)
        
        # Calculate minimum bid (must beat current highest)
        if self.stock_item.bids:
            min_bid = max(min_bid, max(self.stock_item.bids.values()) + 1)
        
        modal = BidModal(self.market, self.stock_item, min_bid)
        await interaction.response.send_modal(modal)
        
        # Wait for modal completion
        await modal.wait()
        
        # Refresh the view to show updated bids
        if modal.bid_placed:
            # Reload the stock item with updated bids
            from Steward.models.objects.auctionHouse import StockItem
            updated_stock = await StockItem.fetch(
                self.market._bot.db,
                self.stock_item.id,
                load_bids=True
            )
            if updated_stock:
                self.stock_item = updated_stock
                
            # Update the view
            updated_view = ItemDetailView(self.market, self.stock_item, self.user)
            await interaction.edit_original_response(view=updated_view)

    @ui.button.callback("back_button")
    async def on_back(self, button: ui.Button, interaction: discord.Interaction):
        """Go back to item selection"""
        select_view = ItemSelectionView(self.market, self.user)
        await interaction.response.edit_message(view=select_view)


class BidModal(ui.DesignerModal):
    """Modal for placing a bid on an item"""
    
    def __init__(self, market: "AuctionHouse", stock_item: "StockItem", min_bid: float):
        self.market = market
        self.stock_item = stock_item
        self.min_bid = min_bid
        self.bid_placed = False
        
        super().__init__(
            ui.Label(
                f"Bid Amount (minimum {int(min_bid):,})",
                ui.InputText(
                    placeholder=f"Enter amount (min {int(min_bid):,})",
                    custom_id="bid_amount",
                    required=True,
                    style=discord.InputTextStyle.short
                )
            ),
            title=f"Bid on {stock_item.item.name if stock_item.item else 'Item'}"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Process the bid"""
        from Steward.models.objects.player import Player
        from Steward.models.objects.character import Character
        
        # Get bid amount
        bid_input = self.get_item("bid_amount")
        
        try:
            bid_amount = int(bid_input.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Bid must be a valid number.",
                ephemeral=True
            )
            return
        
        # Validate minimum bid
        if bid_amount < self.min_bid:
            await interaction.response.send_message(
                f"❌ Bid must be at least {int(self.min_bid):,}.",
                ephemeral=True
            )
            return
        
        # Get player and their active character
        player = await Player.get_or_create(self.market._bot.db, interaction.user)
        character = player.primary_character
        
        if not character:
            await interaction.response.send_message(
                "❌ You need an active character to place bids.",
                ephemeral=True
            )
            return
        
        # Check if character has enough currency
        if character.currency < bid_amount:
            await interaction.response.send_message(
                f"❌ Insufficient funds. You have {character.currency:,}, but need {bid_amount:,}.",
                ephemeral=True
            )
            return
        
        # Place the bid
        if not self.stock_item.bids:
            self.stock_item.bids = {}
        
        self.stock_item.bids[character] = bid_amount
        await self.stock_item.upsert_bids(self.stock_item.bids)
        
        self.bid_placed = True
        
        await interaction.response.send_message(
            f"✅ Bid of {bid_amount:,} placed successfully!",
            ephemeral=True
        )
                    