import discord
import discord.ui as ui



from typing import TYPE_CHECKING
from Steward.models.embeds import ErrorEmbed
from Steward.models.modals import PromptModal
from Steward.models.objects.activity import Activity
from Steward.models.objects.character import Character
from Steward.models.objects.exceptions import StewardError
from Steward.models.objects.player import Player
from Steward.models.objects.request import Request
from Steward.models.views import StewardView
from Steward.utils.viewUitils import get_character_header, get_character_request_sections, get_character_select_option, get_player_header
from constants import DENIED_EMOJI

if TYPE_CHECKING:
    from Steward.bot import StewardBot, StewardContext


class BaseRequestView(StewardView):
    __copy_attrs__ = [
        "bot", "ctx", "selected_player", "character",
        "player", "request"
    ]

    bot: "StewardBot"
    ctx: "StewardContext"
    request: Request
    player: Player
    character: Character
    selected_player: Player
        

class Requestview(BaseRequestView):
    def __init__(self, bot: "StewardBot", ctx: "StewardContext", player: Player, character: Character, **kwargs):
        self.owner = ctx.author
        self.bot = bot
        self.ctx = ctx
        self.player = player
        self.character = character

        self.request = kwargs.get(
            'request',
            Request(
                self.bot,
                guild_id=ctx.guild.id,
                player_id=player.id,
                channel_id=ctx.channel.id,
                player_characters={player: [character]}
            )
        )
        self.selected_player = kwargs.get('selected_player')

        content = []
        separator = ui.Separator()

        container = ui.Container(
            get_character_header(self.player, self.character),
            separator
        )

        get_character_request_sections(container, self.request, self._remove_character)

        if self.request.notes and self.request.notes != "":
            container.add_item(
                ui.TextDisplay(
                    f"# Notes\n{self.request.notes}"
                )
            )

        content.append(container)

        player_select = ui.Select(
            discord.ComponentType.user_select,
            placeholder="Select any additional players",
            required=False,
            custom_id="add_player"
        )
        player_select.callback = self._on_player_select

        content.append(
            ui.ActionRow(player_select)
        )


        if self.selected_player:
            character_select = get_character_select_option(self.selected_player,None, self._on_char_select, enable_def=False)
            content.append(ui.ActionRow(character_select))
            

        # Button Row
        button_row =[]

        # Request Notes
        notes_button = ui.Button(
            label="Add Notes",
            style=discord.ButtonStyle.green
        )
        notes_button.callback = self._notes_button
        button_row.append(notes_button)

        # Submit Button
        submit_button = ui.Button(
            label="Submit",
            style=discord.ButtonStyle.blurple
        )
        submit_button.callback = self._submit_button
        button_row.append(submit_button)

        # Exit
        exit_button = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.red
        )
        exit_button.callback = self.timeout_callback
        button_row.append(exit_button)

        content.append(
            ui.ActionRow(*button_row)
        )
        super().__init__(*content)
        
    async def _on_player_select(self, interaction: discord.Interaction):
        member = self.get_item("add_player").values[0]
        if member:
            self.selected_player = await Player.get_or_create(self.bot.db, member)

            if not self.selected_player.active_characters:
                await interaction.channel.send(embed=ErrorEmbed(f"`{self.selected_player.display_name}` has not active characters"))
                return await self.refresh_content(interaction)

            if self.selected_player not in self.request.player_characters:
                self.request.player_characters[self.selected_player] = []

        else:
            self.selected_player = None

        await self.refresh_content(interaction)

    async def _on_char_select(self, interaction: discord.Interaction):
        char = self.get_item("char_select").values[0]

        character = next(
            (c for c in self.selected_player.active_characters if str(c.id) == char),
            None
        )

        if self.selected_player not in self.request.player_characters:
            self.request.player_characters[self.selected_player] = []

        if character and self.selected_player in self.request.player_characters and character not in self.request.player_characters[self.selected_player]:
            self.request.player_characters[self.selected_player].append(character)

        await self.refresh_content(interaction)

    async def _notes_button(self, interaction: discord.Interaction):
        modal = PromptModal(
            "Request Notes",
            self.request.notes,
            "Request Notes"
        )

        await self.prompt_modal(modal, interaction)

        self.request.notes = modal.value
        
        await self.refresh_content(interaction)

    async def _submit_button(self, interaction: discord.Interaction):
        self.request = await self.request.upsert()

        self.bot.dispatch("new_request", self.request)
        await self.on_timeout()


    async def _remove_character(self, interaction: discord.Interaction):
        char_id = interaction.data["custom_id"][7:]

        for p, c in self.request.player_characters.items():
            for char in c:
                if str(char.id) == char_id:
                    c.remove(char)

            if not c and p != self.player:
                del self.request.player_characters[p]
                break

        await self.refresh_content(interaction)
        

class BaseRequestReviewView(ui.DesignerView):
    def __init__(self, bot: "StewardBot", **kwargs):
        self._bot = bot

        self.request: Request = kwargs.get('request')
        super().__init__(
            ui.TextDisplay("Coming soon!"),
            timeout=None
        )

    @classmethod
    def new(cls, bot: "StewardBot"):
        inst = cls(bot)
        return inst
    
    async def build_content(self):
        player = await self.request.player()
        self.clear_items()

        container = ui.Container(
                ui.TextDisplay("# REQUEST FOR:"),
                get_player_header(player),
                ui.Separator()
            )

        

        get_character_request_sections(container, self.request)

        self.add_item(container)

        if self.request.notes:
            self.add_item(ui.TextDisplay(f"# Notes\n{self.request.notes}"))
        

    async def _button_1(self, interaction: discord.Interaction):
        if not self.request:
            self.request = await Request.fetch(self.bot, interaction.message.id)
        
        if not self.request:
            raise StewardError("Request not Found")
        
        self.bot.dispatch("request_button_1")
    


