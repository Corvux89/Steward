import uuid

import discord.ui as ui
import discord

from Steward.models.objects.auctionHouse import AuctionHouse, StockItem
from Steward.models.objects.character import Character

class BidModal(ui.DesignerModal):
    def __init__(
        self,
        character: "Character",
        house: "AuctionHouse",
        stock_item: "StockItem",
        min_bid: float,
        characters: list["Character"] = None,
    ):
        self.character = character
        self.characters = characters or []
        self.house = house
        self.stock_item = stock_item
        self.min_bid = min_bid
        self.bid_placed = False

        components = []
        if self.character is None and self.characters:
            options = [
                discord.SelectOption(label=char.name, value=str(char.id))
                for char in self.characters
            ]
            components.append(
                ui.Label(
                    "Character",
                    ui.Select(
                        placeholder="Choose a character...",
                        options=options,
                        custom_id="character_select"
                    )
                )
            )

        components.append(
            ui.Label(
                f"Bid amount (minimum {int(min_bid):,})",
                ui.InputText(
                    placeholder=f"Enter amount (min {int(min_bid):,})",
                    custom_id="bid_amount"
                )
            )
        )

        super().__init__(
            *components,
            title=f"Bid on {self.stock_item.item.name if stock_item.item else 'Item'}"
        )

    async def callback(self, interaction: discord.Interaction):
        if self.character is None and self.characters:
            selection = self.get_item("character_select").values
            if not selection:
                await interaction.response.send_message(
                    "You must choose a character.",
                    ephemeral=True
                )
                return
            try:
                selected_id = uuid.UUID(selection[0])
            except ValueError:
                await interaction.response.send_message(
                    "Invalid character.",
                    ephemeral=True
                )
                return

            self.character = next(
                (c for c in self.characters if c.id == selected_id),
                None
            )

            if not self.character:
                await interaction.response.send_message(
                    "Character not found.",
                    ephemeral=True
                )
                return

        bid_amount_item = self.get_item("bid_amount")
        bid_amount = getattr(bid_amount_item, "value", None)
        if bid_amount is None:
            bid_amount = bid_amount_item

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

        # Check for existing bid from this character and update it
        for char in list(self.stock_item.bids.keys()):
            if char.id == self.character.id:
                del self.stock_item.bids[char]
                break

        self.stock_item.bids[self.character] = bid_amount
        await self.stock_item.upsert_bids(self.stock_item.bids)

        self.bid_placed = True
        
        await interaction.response.send_message(
            f"Bid placed successfully!",
            ephemeral=True
        )
        


class UpdateBidModal(ui.DesignerModal):
    def __init__(
        self,
        house: "AuctionHouse",
        stock_item: "StockItem",
        character: "Character",
    ):
        self.house = house
        self.stock_item = stock_item
        self.character = character
        self.bid_updated = False
        self.bid_removed = False
        
        current_bid = stock_item.bids.get(character, 0)
        min_bid = house.minimum_bid(stock_item.item)
        
        # Calculate minimum to beat current highest
        if stock_item.bids:
            highest = max(stock_item.bids.values())
            if highest > current_bid:
                min_bid = highest + 1
            else:
                min_bid = current_bid + 1
        
        components = [
            ui.Label(
                f"New bid amount (minimum {int(min_bid):,})",
                ui.InputText(
                    placeholder=f"Leave empty or set to 0 to remove bid, or enter new amount",
                    custom_id="bid_amount",
                    required=False
                )
            )
        ]
        
        super().__init__(
            *components,
            title=f"Update Bid: {stock_item.item.name if stock_item.item else 'Item'}"
        )
    
    async def callback(self, interaction: discord.Interaction):
        bid_amount_item = self.get_item("bid_amount")
        bid_amount = getattr(bid_amount_item, "value", None)
        
        # If empty, remove the bid
        if not bid_amount or bid_amount.strip() == "" or bid_amount == "0":
            if self.character in self.stock_item.bids:
                del self.stock_item.bids[self.character]
                await self.stock_item.upsert_bids(self.stock_item.bids)
                self.bid_removed = True
                await interaction.response.send_message("Bid removed.", ephemeral=True)
            else:
                await interaction.response.send_message("Bid not found.", ephemeral=True)
            return
        
        try:
            bid_amount = int(bid_amount)
        except:
            await interaction.response.send_message(
                "Bid must be a valid number.",
                ephemeral=True
            )
            return
        
        current_bid = self.stock_item.bids.get(self.character, 0)
        min_bid = self.house.minimum_bid(self.stock_item.item)
        
        # Calculate minimum to beat current highest
        if self.stock_item.bids:
            highest = max(self.stock_item.bids.values())
            if highest > current_bid:
                min_bid = highest + 1
            else:
                min_bid = current_bid + 1
        
        if bid_amount < min_bid:
            await interaction.response.send_message(
                f"Bid must be at least {int(min_bid):,}.",
                ephemeral=True
            )
            return

        if self.character.currency < bid_amount:
            await interaction.response.send_message(
                f"Insufficient funds. You only have {self.character.currency:,}",
                ephemeral=True
            )
            return
        
        # Update the bid
        self.stock_item.bids[self.character] = bid_amount
        await self.stock_item.upsert_bids(self.stock_item.bids)
        
        self.bid_updated = True
        
        await interaction.response.send_message(
            f"Bid updated to {bid_amount:,}!",
            ephemeral=True
        )