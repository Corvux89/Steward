import discord.ui as ui
import discord

from Steward.models.objects.auctionHouse import AuctionHouse, StockItem
from Steward.models.objects.character import Character

class BidModal(ui.DesignerModal):
    def __init__(self, character: "Character", house: "AuctionHouse", stock_item: "StockItem", min_bid: float):
        self.character = character
        self.house = house
        self.stock_item = stock_item
        self.min_bid = min_bid
        self.bid_placed = False

        super().__init__(
            ui.Label(
                f"Bid amount (minimum {int(min_bid):,})",
                ui.InputText(
                    placeholder=f"Enter amount (min {int(min_bid):,})",
                    custom_id="bid_amount"
                )
            ),
            title=f"Bid on {self.stock_item.item.name if stock_item.item else 'Item'}"
        )

    async def callback(self, interaction: discord.Interaction):
        bid_amount =- self.get_item("bid_amount")

        try:
            bid_amount = int(bid_amount)
        except:
            await interaction.response.send_message(
                "Bid must be a valid number.",
                ephemeral=True
            )
            return
        
        if bid_amount < self.min_bid:
            await interaction.response.send_message(
                f"Bid must be at least {int(self.min_bid):,}.",
                ephemeral=True
            )

        if self.character.currency < bid_amount:
            await interaction.response.send_message(
                f"Insufficient funds. You only have {self.character.currency:,}",
                ephemeral=True
            )

        if not self.stock_item.bids:
            self.stock_item.bids = {}

        self.stock_item.bids[self.character] = bid_amount
        await self.stock_item.upsert_bids(self.stock_item.bids)

        self.bid_placed = True
        
        await interaction.response.send_message(
            f"Bid placed successfully!",
            ephemeral=True
        )
        