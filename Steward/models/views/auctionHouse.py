import discord
import discord.ui as ui
from datetime import timezone
from typing import TYPE_CHECKING
import uuid

from Steward.models.modals.auctionHouse import BidModal
from Steward.models.objects.exceptions import CharacterNotFound
from Steward.models.objects.player import Player
from Steward.models.views import StewardView
from Steward.models.modals import PromptModal
from constants import APPROVAL_EMOJI

if TYPE_CHECKING:
    from Steward.models.objects.auctionHouse import AuctionHouse, StockItem, Item
    from Steward.models.objects.character import Character


class AuctionHouseView(StewardView):
    """Main public view for the auction house showing all shelves and items"""

    CUSTOM_ID_PREFIX = "ah"

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
    
    def __init__(self, house: "AuctionHouse", owner=None):
        self.house = house
        refresh_time = self.house.next_reroll_at()

        if refresh_time:
            refresh_str = f"<t:{int(refresh_time.timestamp())}:R>"
        else:
            refresh_str = f"`Soon`"
        
        container = ui.Container(
            ui.TextDisplay(f"## {self.house.name}"),
            ui.TextDisplay(f"-# Inventory refreshes: {refresh_str}"),
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
                    qty_bid_on = len([s for s in stock_items if s.bids])
                    
                    min_bid = self.house.minimum_bid(item)

                    item_text = ui.TextDisplay(
                        f"- **{item.name}**: {qty_available} available ({qty_bid_on} being bid on) - Min Bid: {min_bid:,.0f}"
                    )

                    item_button = ui.Button(
                        emoji="🪙",
                        custom_id=self._make_custom_id("bid", shelf.id, item.id)
                    )
                    item_button.callback = self._bid_button
                    
                    container.add_item(
                        ui.Section(
                            item_text,
                            accessory=item_button
                        )
                    )

        # Add separator and my bids button at bottom
        container.add_item(ui.Separator())
        
        my_bids_button = ui.Button(
            label="View My Bids",
            style=discord.ButtonStyle.primary,
            custom_id=self._make_custom_id("my_bids")
        )
        my_bids_button.callback = self._view_my_bids_button
        
        button_row = ui.ActionRow(my_bids_button)
        container.add_item(button_row)

        super().__init__(container, timeout=None)

    async def _bid_button(self, interaction: discord.Interaction):
        action, parts = self._parse_custom_id(interaction.data.get("custom_id"))
        if action != "bid" or len(parts) < 2:
            await interaction.response.send_message("Invalid action.", ephemeral=True)
            return

        try:
            shelf_id = uuid.UUID(parts[0])
            item_id = uuid.UUID(parts[1])
        except ValueError:
            await interaction.response.send_message("Invalid item.", ephemeral=True)
            return

        # Find all stock items for this item on this shelf
        item_stock_items = [
            i for i in self.house.inventory 
            if i.item_id == item_id and i.shelf_id == shelf_id
        ]

        if not item_stock_items:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return

        player = await Player.get_or_create(self.house._bot.db, interaction.user)

        # If only one, proceed directly
        if len(item_stock_items) == 1:
            stock_item = item_stock_items[0]
            item_detail_view = ItemDetailView(self.house, stock_item, player)
            await interaction.response.send_message(
                view=item_detail_view,
                ephemeral=True
            )
        else:
            # Show selector if multiple
            select_view = StockItemSelectView(self.house, item_stock_items, player)
            await interaction.response.send_message(
                view=select_view,
                ephemeral=True
            )

    async def _view_my_bids_button(self, interaction: discord.Interaction):
        player = await Player.get_or_create(self.house._bot.db, interaction.user)
        my_bids_view = MyBidsView(self.house, player)
        await interaction.response.send_message(
            view=my_bids_view,
            ephemeral=True
        )

class ItemDetailView(StewardView):
    """Detailed view of a specific stock item with bidding options"""
    __copy_attrs__ = [
        "house", "stock_item", "player"
    ]
    
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
                    f"**Auction Ends:** <t:{timestamp}:R>"
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
                custom_id=AuctionHouseView._make_custom_id("place_bid")
            )
        place_bid_button.callback = self._place_bid_button

        button_row = ui.ActionRow(
            place_bid_button,
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

        characters = None
        if len(self.player.active_characters) == 1:
            self.character = self.player.primary_character
        else:
            self.character = None
            characters = list(self.player.active_characters)

        modal = BidModal(self.character, self.house, self.stock_item, min_bid, characters=characters)
        await self.prompt_modal(modal, interaction)
        
        # Refresh the view to show updated bids
        if modal.bid_placed:
            # Reload the stock item with updated bids
            from Steward.models.objects.auctionHouse import StockItem
            updated_stock = await StockItem.fetch(
                self.house._bot.db,
                self.stock_item.id
            )
            if updated_stock:
                self.stock_item = updated_stock
                
            # Update the view
            await self.house.refresh_view()
            await self.refresh_content(interaction)


class StockItemSelectView(StewardView):
    """View for selecting which stock item to bid on when multiple are available"""
    
    def __init__(self, house: "AuctionHouse", stock_items: list["StockItem"], player: "Player"):
        self.house = house
        self.stock_items = stock_items
        self.player = player
        self.owner = self.player
        
        container = ui.Container(
            ui.TextDisplay("**Select which item to bid on:**"),
            ui.Separator()
        )
        
        # Display each stock item with detailed information
        for idx, stock_item in enumerate(stock_items, 1):
            bid_count = len(stock_item.bids) if stock_item.bids else 0
            
            # Build information text
            info_text = f"**{stock_item.item.name} {idx}**\n"
            info_text += f"Bids: {bid_count}\n"
            
            if stock_item.bids:
                highest_bid = max(stock_item.bids.values())
                highest_bidder = next((char.name for char, bid in stock_item.bids.items() if bid == highest_bid), "Unknown")
                info_text += f"Highest: {highest_bid:,.0f} ({highest_bidder})"

                end_time = house.auction_end_at(stock_item)
                if end_time:
                    timestamp = int(end_time.timestamp())
                    info_text += f"\nEnds: <t:{timestamp}:R>"
            else:
                info_text += "No bids yet - Start the bidding!"
            
            # Create button for this item
            select_button = ui.Button(
                emoji=APPROVAL_EMOJI[0],
                style=discord.ButtonStyle.secondary,
                custom_id=AuctionHouseView._make_custom_id("select_stock", stock_item.id)
            )
            select_button.callback = self._make_select_callback(stock_item)
            
            container.add_item(
                ui.Section(
                    ui.TextDisplay(info_text),
                    accessory=select_button
                )
            )
            
            if idx < len(stock_items):
                container.add_item(ui.Separator())
        
        super().__init__(container, timeout=60)

    def _make_select_callback(self, stock_item: "StockItem"):
        async def callback(interaction: discord.Interaction):
            # Show the item detail view
            item_detail_view = ItemDetailView(self.house, stock_item, self.player)
            await interaction.response.edit_message(
                view=item_detail_view
            )
        return callback


class MyBidsView(StewardView):
    """View showing player's bids and allowing bid removal"""
    __copy_attrs__ = [
        "house", "player"
    ]
    
    def __init__(self, house: "AuctionHouse", player: "Player"):
        self.house = house
        self.player = player
        self.owner = player
        
        container = ui.Container(
            ui.TextDisplay("**Your Bids**"),
            ui.Separator()
        )
        
        # Get all bids from player's characters
        player_character_ids = {char.id for char in player.active_characters}
        
        # Build a map of items to bids from this player's characters
        player_bids = {}
        for stock_item in house.inventory:
            for character, bid_amount in (stock_item.bids or {}).items():
                if character.id in player_character_ids:
                    if stock_item.item_id not in player_bids:
                        player_bids[stock_item.item_id] = []
                    player_bids[stock_item.item_id].append({
                        'character': character,
                        'bid_amount': bid_amount,
                        'stock_item': stock_item
                    })
        
        if not player_bids:
            container.add_item(ui.TextDisplay("*You have no active bids*"))
        else:
            bid_count = 0
            for item_id, bids in player_bids.items():
                item = next((i for i in house.items if i.id == item_id), None)
                if not item:
                    continue
                
                for bid_info in bids:
                    info_text = f"**{item.name}**\n"
                    info_text += f"{bid_info['character'].name}: {bid_info['bid_amount']:,.0f}"
                    
                    # Check if they are winning
                    is_winning = bid_info['bid_amount'] == max(bid_info['stock_item'].bids.values())
                    if is_winning:
                        info_text += " *(Currently Winning)*"
                    
                    # Add auction end time if available
                    end_time = house.auction_end_at(bid_info['stock_item'])
                    if end_time:
                        timestamp = int(end_time.timestamp())
                        info_text += f"\nEnds: <t:{timestamp}:R>"
                    
                    # Create update bid button
                    update_button = ui.Button(
                        label="Update Bid",
                        style=discord.ButtonStyle.primary if is_winning else discord.ButtonStyle.secondary,
                        custom_id=AuctionHouseView._make_custom_id("update_bid", bid_info['stock_item'].id, bid_info['character'].id)
                    )
                    update_button.callback = self._make_update_bid_callback(bid_info['stock_item'], bid_info['character'])
                    
                    container.add_item(
                        ui.Section(
                            ui.TextDisplay(info_text),
                            accessory=update_button
                        )
                    )
                    
                    bid_count += 1
                    if bid_count < sum(len(bids_list) for bids_list in player_bids.values()):
                        container.add_item(ui.Separator())
        
        super().__init__(container, timeout=300)
    
    def _make_update_bid_callback(self, stock_item: "StockItem", character: "Character"):
        async def callback(interaction: discord.Interaction):
            # Show modal to update or remove bid
            from Steward.models.modals.auctionHouse import UpdateBidModal
            modal = UpdateBidModal(self.house, stock_item, character)
            await self.prompt_modal(modal, interaction)
            
            # Refresh views if bid was updated or removed
            if modal.bid_updated or modal.bid_removed:
                await self.house.refresh_view()
                await self.refresh_content(interaction)
        
        return callback


