import discord
import discord.ui as ui



from typing import TYPE_CHECKING, Union
from Steward.models.embeds import ErrorEmbed
from Steward.models.modals import PromptModal
from Steward.models.objects.activity import Activity
from Steward.models.objects.character import Character
from Steward.models.objects.enum import LogEvent
from Steward.models.objects.exceptions import StewardError
from Steward.models.objects.log import StewardLog
from Steward.models.objects.player import Player
from Steward.models.objects.request import Request
from Steward.models.views import StewardView, confirm_view
from Steward.utils.discordUtils import try_delete
from Steward.utils.viewUitils import get_activity_select_option, get_character_header, get_character_request_sections, get_character_select_option, get_player_header
from constants import CHANNEL_BREAK, DENIED_EMOJI

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
    def __init__(self, bot: "StewardBot", ctx: Union["StewardContext", discord.Interaction], player: Player, character: Character, **kwargs):
        self.owner = ctx.user
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
                player_channel_id=ctx.channel.id,
                player_message=ctx.message,
                server=ctx.server if hasattr(ctx, "server") else None,
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
        exit_button.callback = self._cancel_button
        button_row.append(exit_button)

        content.append(
            ui.ActionRow(*button_row)
        )
        super().__init__(*content)

    async def on_timeout(self):
        if self.request.staff_message:
            request = await Request.fetch(self.bot, self.request.staff_message_id)
            if request:
                view = PlayerRequestView(self.bot, request=request)
                await view.build_content()
                try:
                    await  self.message.edit(view=view)
                except:
                    pass
        else:
            if (
            not self._message
            or self._message.flags.ephemeral
            or (self._message.channel.type == discord.ChannelType.private)
            ):
                message = self.parent
            else:
                message = self.message

            if message:
                self.remove_all_buttons_and_action_rows()

                try:
                    await self.message.edit(view=self)
                except:
                    pass

                if self.delete_on_timeout:
                    await try_delete(message)

    async def _cancel_button(self, interaction: discord.Interaction):
        if self.request.staff_message_id:
            request = await Request.fetch(self.bot, self.request.staff_message_id)
            view = PlayerRequestView(self.bot, request=request)
            await view.build_content()
            
            if interaction.response.is_done():
                await interaction.edit_original_message(view=view)
            else:
                await interaction.response.edit_message(view=view)
        else:
            await self.on_timeout()
        
    async def _on_player_select(self, interaction: discord.Interaction):
        member = self.get_item("add_player").values[0]
        if member:
            self.selected_player = await Player.get_or_create(self.bot.db, member)

            if not self.selected_player.active_characters:
                await interaction.channel.send(embed=ErrorEmbed(f"No character information found for `{self.selected_player.mention}`"))
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
        self.request.player_message_id = interaction.message.id
        self.request.player_message = interaction.message
        self.request = await self.request.upsert()

        view = PlayerRequestView(self.bot, request=self.request)

        if interaction.response.is_done():
                await interaction.edit_original_message(view=view)
        else:
            await interaction.response.edit_message(view=view)

        
        self.bot.dispatch("new_request", self.request)

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
        

class StaffRequestView(StewardView):
    __copy_attrs__ = [
        "bot", "request", "activity"
    ]

    async def interaction_check(self, interaction: discord.Interaction):
        return True
    
    async def refresh_content(self, interaction: discord.Interaction):
        view = StaffRequestView(self.bot, request=self.request, activity=self.activity)

        if interaction.response.is_done():
            await interaction.edit_original_message(view=view)
        else:
            await interaction.response.edit_message(view=view)

    def __init__(self, bot: "StewardBot", **kwargs):
        self.bot = bot

        self.request: Request = kwargs.get('request')
        self.activity = kwargs.get('activity')

        container = ui.Container(
            ui.TextDisplay("## REQUEST FROM"),
            get_player_header(self.request.primary_player),
            ui.TextDisplay(f"**From Channel**: {self.request.player_channel.jump_url}"),
            ui.Separator()
        )

        get_character_request_sections(container, self.request)

        if self.request.notes:
            container.add_item(
                ui.TextDisplay(f"## Notes\n{self.request.notes}")
            )

        activity_select = get_activity_select_option(self.request.server, self.activity, self._activity_select)

        # Approve Button
        approve_button = ui.Button(
            label="Approve",
            style=discord.ButtonStyle.green,
            custom_id="approve_request"
        )
        approve_button.callback = self._approve_button

        # Cancel Button 
        cancel_button = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.red,
            custom_id="cancel_request"
        )
        cancel_button.callback = self._cancel_button

        super().__init__(
            container,
            ui.ActionRow(activity_select),
            ui.ActionRow(approve_button, cancel_button),
            timeout=None
        )

    async def _activity_select(self, interaction: discord.Interaction):
        act = interaction.data.get('values', [])[0]
        self.activity = self.request.server.get_activity(act)

        await self.refresh_content(interaction)

    async def _cancel_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if await confirm_view(
            interaction,
            "Are you sure you want to cancel this request?",
        ) == True:
            await self.request.delete()

    async def _approve_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not self.activity:
            return await interaction.followup.send("Select an activity first", ephemeral=True)
        
        if await confirm_view(
            interaction,
            f"Approve this request, and log it as `{self.activity.name}`?"
        ) == True:
            await self.request.approve(self.bot, self.activity, interaction.user)
        else:
            await self.refresh_content(interaction)


class PlayerRequestView(StewardView):
    __copy_attrs__ = [
        "bot", "request"
    ]

    def __init__(self, bot: "StewardBot", **kwargs):
        self.bot = bot

        self.request: Request = kwargs.get('request')

        self.owner = self.request.primary_player

        container = ui.Container(
            ui.TextDisplay("## Request Submitted!"),
            get_player_header(self.request.primary_player),
            ui.Separator()
        )

        get_character_request_sections(container, self.request)

        if self.request.notes:
            container.add_item(
                ui.TextDisplay(f"## Notes\n{self.request.notes}")
            )

        # Edit Button
        edit_button = ui.Button(
            label="Edit request",
            style=discord.ButtonStyle.green,
            custom_id="edit_request"
        )
        edit_button.callback = self._edit_button

        # Cancel Button
        cancel_button = ui.Button(
            label="Cancel request",
            style=discord.ButtonStyle.red,
            custom_id="cancel_request"
        )
        cancel_button.callback = self._cancel_button

        super().__init__(
            container,
            ui.ActionRow(edit_button, cancel_button),
            timeout=None
        )

    async def _edit_button(self, interaction: discord.Interaction):
        view = Requestview(self.bot, interaction, self.request.primary_player, self.request.primary_character, request=self.request)
        await interaction.message.edit(view=view)

    async def _cancel_button(self, interaction: discord.Interaction):
        if await confirm_view(
            interaction,
            "Are you sure you want to cancel this request?"
        ) == True:                
            await self.request.delete()
        
class LoggedView(ui.DesignerView):
    def __init__(self, request: Request, activity: Activity, log_user: discord.User):
        container = ui.Container(
            ui.TextDisplay(f"## {activity.name} {activity.verb}"),
            get_player_header(request.primary_player),
            ui.Separator()
        )

        if request.notes:
            container.add_item(
                ui.TextDisplay(f"## Activity Title\n{request.notes}")
            )

        get_character_request_sections(container, request, header="###")

        container.add_item(
            ui.TextDisplay(f"-# {activity.name} logged by {log_user.display_name}")
        )

        super().__init__(container)