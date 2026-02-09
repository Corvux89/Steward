import discord
import discord.ui as ui

from Steward.bot import StewardBot
from Steward.models.objects.character import Character
from Steward.models.objects.enum import LogEvent
from Steward.models.objects.log import StewardLog
from Steward.models.objects.player import Player
from Steward.models.objects.servers import Server

class NewCharacterModal(ui.DesignerModal):
    character: Character
    server: Server

    def __init__(
            self,
            character: Character,
            server: Server
    ):
        self.character = character
        self.server = server                

        name_input = ui.Label(
            "Character Name",
            ui.InputText(
                placeholder="Character Name",
                max_length=2000,
                value=self.character.name if self.character.name else "",
                custom_id="char_name"
            )
        )

        species_input = ui.Label(
            "Species",
            ui.InputText(
                placeholder="Species",
                max_length=1000,
                value=self.character.species_str if self.character.species_str else "",
                custom_id="char_species"
            )
        )

        class_input = ui.Label(
            "Class",
            ui.InputText(
                placeholder="Class",
                max_length=1000,
                value=self.character.class_str if self.character else "",
                custom_id="char_class"
            )
        )

        currency_input = ui.Label(
            self.server.currency_str,
            ui.InputText(
                placeholder=str(self.server.currency_str),
                max_length=4,
                value=str(self.character.currency) if self.character.currency else "0",
                custom_id="char_currency"
            )
        )

        level_options = [
            discord.SelectOption(label=str(x), value=str(x), default=True if x==1 else False) for x in range(1,self.server.max_level+1)
        ]
        level_input = ui.Label(
            "Level",
            ui.Select(
                placeholder="Select character level",
                options=level_options,
                custom_id="char_level"
            )
        )

        children = [
            name_input,
            species_input,
            class_input,
            currency_input,
            level_input
        ]
        
        super().__init__(
            *children,
            title="Character Information"
        )

    async def callback(self, interaction):
        self.character.name = self.get_item("char_name").value
        self.character.species_str = self.get_item("char_species").value
        self.character.class_str = self.get_item("char_class").value
        try:
            self.character.currency = int(self.get_item("char_currency").value)
            self.character.level = int(self.get_item("char_level").values[0])
        except:
            pass
        
        self.character.xp = self.server.get_xp_for_level(self.character.level)
        

        await interaction.response.defer()
        self.stop()

class PlayerInformationModal(ui.DesignerModal):
    player: Player
    bot: StewardBot

    def __init__(
            self, 
            bot: StewardBot,
            player: Player,
            admin: bool = False
    ):
        self.bot = bot
        self.player = player
        self.admin = admin

        if self.admin == True:
            staff_points = ui.Label(
                "Staff Points",
                ui.InputText(
                    placeholder="Staff Points",
                    value=getattr(self.player, "staff_points", "0"),
                    custom_id="staff_points",
                    max_length=100
                )
            )

        notes_input = ui.Label(
            "Notes",
            ui.InputText(
                placeholder="Player Notes (Staff use)",
                value=getattr(self.player, "notes", ""),
                style=discord.InputTextStyle.long,
                max_length=2000,
                custom_id="player_notes",
                required=False
            )
        )

        campaign_input = ui.Label(
            "Campaign",
            ui.InputText(
                placeholder="Campaign",
                value=getattr(self.player, "campaign", ""),
                custom_id="player_campaign",
                required=False
            )
        )

        super().__init__(
            notes_input,
            campaign_input,
            title="Player Information"
        )

    async def callback(self, interaction):
        notes = self.get_item("player_notes").value
        campaign = self.get_item("player_campaign").value
        try:
            if self.admin == True:
                staff_points = int(self.get_item("staff_points").value)
            else:
                staff_points = self.player.staff_points
        except:
            staff_points = self.player.staff_points
        
        if self.player.notes != notes or self.player.campaign != campaign or self.player.staff_points != staff_points:
            self.player.notes = notes
            self.player.campaign = campaign
            self.player.staff_points = staff_points
            await self.player.save()

            await StewardLog.create(
                self.bot,
                interaction.user,
                self.player,
                LogEvent.player_update,
                notes="Player information updated"
            )

        await interaction.response.defer()
        self.stop()

class CharacterDemographicsModal(ui.DesignerModal):
    character: Character

    def __init__(
            self,
            character: Character
    ):
        self.character = character

        species_input = ui.Label(
            "Species",
            ui.InputText(
                placeholder="Species",
                max_length=1000,
                value=self.character.species_str if self.character.species_str else "",
                custom_id="char_species"
            )
        )

        class_input = ui.Label(
            "Class",
            ui.InputText(
                placeholder="Class",
                max_length=1000,
                value=self.character.class_str if self.character else "",
                custom_id="char_class"
            )
        )

        super().__init__(
            species_input,
            class_input,
            title="Character Demographics"
        )