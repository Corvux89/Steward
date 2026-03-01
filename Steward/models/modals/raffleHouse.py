import uuid

import discord.ui as ui
import discord

from Steward.models.objects.raffleHouse import Raffle, StockItem
from Steward.models.objects.character import Character

class BuyTicketModal(ui.DesignerModal):
    def __init__(
        self,
        character: "Character",
        house: "Raffle",
        stock_item: "StockItem",
        max_quantity: int,
        characters: list["Character"] = None,
    ):
        self.character = character
        self.characters = characters or []
        self.house = house
        self.stock_item = stock_item
        self.max_quantity = max_quantity
        self.tickets_purchased = False

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
                f"Ticket quantity (max {int(max_quantity):,})",
                ui.InputText(
                    placeholder="Enter quantity",
                    custom_id="ticket_quantity"
                )
            )
        )

        item_name = self.stock_item.item.name if stock_item.item else "Item"
        super().__init__(
            *components,
            title=f"Buy tickets: {item_name}"
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

        quantity_item = self.get_item("ticket_quantity")
        quantity_value = getattr(quantity_item, "value", None)
        if quantity_value is None:
            quantity_value = quantity_item

        try:
            quantity = int(quantity_value)
        except:
            await interaction.response.send_message(
                "Ticket quantity must be a valid number.",
                ephemeral=True
            )
            return

        if quantity <= 0:
            await interaction.response.send_message(
                "Ticket quantity must be greater than 0.",
                ephemeral=True
            )
            return

        if quantity > int(self.max_quantity):
            await interaction.response.send_message(
                f"You can buy at most {int(self.max_quantity):,} ticket(s) right now.",
                ephemeral=True
            )
            return

        success, message = await self.house.purchase_tickets(self.stock_item, self.character, quantity)

        if not success:
            await interaction.response.send_message(message, ephemeral=True)
            return

        self.tickets_purchased = True
        
        await interaction.response.send_message(
            message,
            ephemeral=True
        )


BidModal = BuyTicketModal