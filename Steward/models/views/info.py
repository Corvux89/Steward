import logging
import discord
import discord.ui as ui

from Steward.bot import StewardBot, StewardContext
from Steward.models.modals.player import PlayerInformationModal
from Steward.models.modals import confirm_modal, get_value_modal
from Steward.models.objects.character import Character
from Steward.models.objects.enum import ApplicationType, LogEvent
from Steward.models.objects.log import StewardLog
from Steward.models.objects.player import Player
from Steward.models.views import StewardView
from Steward.utils.discordUtils import try_delete
from Steward.utils.viewUitils import get_character_info_sections, get_character_select_option
from constants import EDIT_EMOJI

log = logging.getLogger(__name__)

# TODO: New Character
# TODO: Reroll Character

class BaseInfoView(StewardView):
    __copy_attrs__ = [
        'bot', 'ctx', 'player', 
        'staff', 'character', 'admin', 
        'new_character', 'reroll_character', 'application_type'
    ]

    bot: StewardBot
    ctx: StewardContext
    player: Player
    staff: bool
    admin: bool
    character: Character
    delete_on_timeout: bool

    async def on_timeout_callback(self, _: discord.Interaction):
        await self.on_timeout()

    async def on_timeout(self):
        if (
            not self._message
            or self._message.flags.ephemeral
            or (self._message.channel.type == discord.ChannelType.private)
        ):
            message = self.parent
        else:
            message = self.message

        if message:
            view = PlayerInfoView.from_menu(self)
            view.remove_all_buttons_and_action_rows()
            await self.message.edit(view=view)

            if self.delete_on_timeout:
                await try_delete(message)


class PlayerInfoView(BaseInfoView):
    def __init__(self, bot: StewardBot, ctx: StewardContext, player: Player, **kwargs):
        self.owner = ctx.author
        self.bot = bot
        self.ctx = ctx
        self.player = player
        self.staff = kwargs.get("staff", False)
        self.admin = kwargs.get("admin", False)
        self.delete_on_timeout = kwargs.get('delete', True)

        content = []
        separator = ui.Separator()

        container = ui.Container(
            ui.Section(
                ui.TextDisplay(f"{self.player.mention}"),
                accessory=ui.Thumbnail(
                    url=f"{self.player.avatar.url}"
                )
            ),
            separator
        )

        content.append(container)

        if self.player.active_characters:
            container.items.extend(get_character_info_sections(self.player, self.ctx.server, self._on_char_swap))

        if self.staff:
            row_1_buttons = []

            player_button = ui.Button(
                label="Player Information",
                custom_id="player_information"
            )

            player_button.callback = self._on_player_info
            row_1_buttons.append(player_button)

            if not self.player.active_characters or len(self.player.active_characters) < self.ctx.server.max_characters(self.player):
                new_character_button = ui.Button(
                    label="New Character",
                    style=discord.ButtonStyle.green,
                    custom_id="new_character"
                )
                # TODO: New Character Callback
                row_1_buttons.append(new_character_button)

            content.append(
                ui.ActionRow(
                    *row_1_buttons
                )
            )

        super().__init__(*content)

    async def _on_char_swap(self, interaction: discord.Interaction):
        char_id = interaction.data["custom_id"]

        character = next(
            (c for c in self.player.active_characters if char_id == str(c.id)),
            None
        )

        self.character = character
        await self.defer_to(CharacterInfoView, interaction)

    async def _on_player_info(self, interaction: discord.Interaction):
        modal = PlayerInformationModal(self.bot, self.player)
        await self.prompt_modal(modal, interaction)

        await self.refresh_content(interaction)

class CharacterInfoView(BaseInfoView):
    def __init__(self, bot: StewardBot, ctx: StewardContext, player: Player, character: Character, **kwargs):
        self.owner = ctx.author
        self.bot = bot
        self.ctx = ctx
        self.player = player
        self.character = character
        self.staff = kwargs.get("staff", False)
        self.admin = kwargs.get("admin", False)
        self.delete_on_timeout = kwargs.get("delete", False)
        
        content = self._build_content()
        super().__init__(*content, **kwargs)
    
    def _build_content(self) -> list:
        """Build and return the view content."""
        content = []
        separator = ui.Separator(divider=True)
        
        # Header section
        container = ui.Container(
            ui.Section(
                ui.TextDisplay(
                    f"{self.character.name} ({self.player.mention})\n"
                    f"-# Level {self.character.level}\n"
                    f"-# {self.character.species_str} {self.character.class_str}"
                ),
                accessory=ui.Thumbnail(
                    url=self.character.avatar_url or self.player.avatar.url
                ),
            ),
            separator
        )

        # Add character info sections
        self._add_nickname_section(container)
        self._add_currency_section(container)
        self._add_xp_section(container)
        self._add_activity_section(container)
        
        content.append(container)

        # Buttons
        row_1 = self._add_button_row_1()

        if row_1:
            content.append(ui.ActionRow(*row_1))
        
        # Character select dropdown
        character_select = get_character_select_option(self.player, self.character, self._on_char_select)
        content.append(ui.ActionRow(character_select))
        
        return content
    
    def _add_nickname_section(self, container: ui.Container):
        """Add nickname display with optional edit button."""
        nickname_display = ui.TextDisplay(f"**Nickname**: {self.character.nickname or '`None`'}")
        
        if self.character.player_id == self.ctx.author.id:
            edit_nickname_button = ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji=EDIT_EMOJI[0],
                custom_id="edit_character_nickname",
            )
            edit_nickname_button.callback = self._on_edit_character_nickname
            container.add_item(ui.Section(nickname_display, accessory=edit_nickname_button))
        else:
            container.add_item(nickname_display)
    
    def _add_currency_section(self, container: ui.Container):
        """Add currency display with optional edit button."""
        currency_display = ui.TextDisplay(
            f"**{self.ctx.server.currency_str}**: {self.character.currency}\n"
        )
    
        if self.staff:
            edit_currency_button = ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji=EDIT_EMOJI[0],
                custom_id="edit_character_currency"
            )
            edit_currency_button.callback = self._on_edit_character_currency
            container.add_item(ui.Section(currency_display, accessory=edit_currency_button))
        else:
            container.add_item(currency_display)
    
    def _add_xp_section(self, container: ui.Container):
        """Add XP display with optional level up button."""
        xp_level = self.ctx.server.get_level_for_xp(self.character.xp)
        xp_display = ui.TextDisplay(
            f"**XP**: {self.character.xp} (Level {xp_level}{' eligible' if xp_level > self.character.level else ''})"
        )
        
        if self.staff:
            edit_xp_button = ui.Button(
                style=discord.ButtonStyle.blurple,
                emoji=EDIT_EMOJI[0],
                custom_id="edit_character_xp"
            )
            edit_xp_button.callback = self._on_edit_character_xp
            container.add_item(ui.Section(xp_display, accessory=edit_xp_button))
        else:
            container.add_item(xp_display)
    
    def _add_activity_section(self, container: ui.Container):
        """Add activity points display if enabled."""
        if self.ctx.server.activity_points:
            activity_point = self.ctx.server.get_activitypoint_for_points(self.character.activity_points)
            activity_level = 'Level 0' if not activity_point else f'Level {activity_point.level})'
            activity_display = ui.TextDisplay(    
                f"**Activity Points**: {self.character.activity_points} ({activity_level})"
            )

            if self.admin:
                edit_ap_button = ui.Button(
                    style=discord.ButtonStyle.blurple,
                    emoji=EDIT_EMOJI[0],
                    custom_id="edit_character_ap"
                )
                edit_ap_button.callback = self._on_edit_activity_points
                container.add_item(ui.Section(activity_display, accessory=edit_ap_button))
            else:
                container.add_item(activity_display)

    def _add_button_row_1(self):
        buttons = []

        if self.character.player_id == self.ctx.author.id:
            avatar_button = ui.Button(
                label="Update Avatar",
                style=discord.ButtonStyle.blurple,
                custom_id="character_avatar"
            )
            avatar_button.callback = self._on_edit_character_avatar
            buttons.append(avatar_button)

        if self.staff:
            level_up_button = ui.Button(
                label="Level up!",
                style=discord.ButtonStyle.green,
                custom_id="character_lvel"
            )
            level_up_button.callback = self._on_character_level_up
            buttons.append(level_up_button)

        if self.admin:
            inactivate_button = ui.Button(
                label="Inactivate",
                style=discord.ButtonStyle.red,
                custom_id="character_inactivate"
            )
            inactivate_button.callback = self._on_character_inactivate
            buttons.append(inactivate_button)

        return buttons
    
    async def _on_char_select(self, interaction: discord.Interaction):
        char = self.get_item("char_select").values[0]

        if char == "def":
            await self.defer_to(PlayerInfoView, interaction)
            return

        character = next(
            (c for c in self.player.active_characters if str(c.id) == char),
            None
        )
        self.character = character
        
        await self.defer_to(CharacterInfoView, interaction)

    async def _on_edit_character_nickname(self, interaction: discord.Interaction):
        old_nick = self.character.nickname
        new_nick = await get_value_modal(
            interaction,
            "Nickname",
            old_nick,
            "Character Nickname",
            length=1000,
            required=False
        )

        if new_nick is not None and old_nick != new_nick:
            self.character.nickname = new_nick

            await StewardLog.create(
                self.bot,
                self.ctx.author,
                self.player,
                LogEvent.edit_character,
                character=self.character,
                notes=f"Nickname update: `{old_nick}` -> `{new_nick}`"
            )
        await self.refresh_content(interaction)

    async def _on_edit_character_avatar(self, interaction: discord.Interaction):
        old_avatar = self.character.avatar_url or ""
        new_avatar = await get_value_modal(
            interaction,
            "Avatar URL",
            old_avatar,
            "Character Avatar",
            length=2000,
            required=False
        )

        if new_avatar is not None and old_avatar != new_avatar:
            # Intentionally not logging this
            self.character.avatar_url = new_avatar
            await self.character.upsert()

        await self.refresh_content(interaction)

    async def _on_edit_character_currency(self, interaction: discord.Interaction):
        old_currency = self.character.currency
        new_currency = await get_value_modal(
            interaction,
            self.ctx.server.currency_str,
            str(old_currency),
            f"Character {self.ctx.server.currency_str}",
            integer=True,
            length=100
        )

        if new_currency is not None and old_currency != new_currency:
            difference = new_currency - old_currency

            await StewardLog.create(
                self.bot,
                self.ctx.author,
                self.player,
                LogEvent.edit_character,
                character=self.character,
                currency=difference,
                notes=f"Currency Update: `{old_currency}` -> `{new_currency}` ({difference})"
            )

        await self.refresh_content(interaction)

    async def _on_edit_character_xp(self, interaction: discord.Interaction):
        old_xp = self.character.xp
        new_xp = await get_value_modal(
            interaction,
            "XP",
            str(old_xp),
            "Character XP",
            integer=True,
            length=10
        )

        if new_xp is not None and old_xp != new_xp:
            difference = new_xp - old_xp

            await StewardLog.create(
                self.bot,
                self.ctx.author,
                self.player,
                LogEvent.edit_character,
                character=self.character,
                xp=difference,
                notes=f"XP Update: `{old_xp}` -> `{new_xp}` ({difference})"
            )

        await self.refresh_content(interaction)

    async def _on_edit_activity_points(self, interaction: discord.Interaction):
        old_ap = self.character.activity_points
        new_ap = await get_value_modal(
            interaction,
            "Activity Points",
            str(old_ap),
            "Character Activity Points",
            integer=True,
            length=10
        )

        if new_ap is not None and old_ap != new_ap:
            if await confirm_modal(
                interaction,
                (
                    f"Adjusting a characters activity points, will not reward them if they change levels.\n\n"
                    f"Do you wish to proceed?"
                )
            ):
                self.character.activity_points = new_ap
                
                await StewardLog.create(
                    self.bot,
                    self.ctx.author,
                    self.player,
                    LogEvent.edit_character,
                    character=self.character,
                    notes=f"Activity Point Update: `{old_ap}` -> {new_ap}"
                )

        await self.refresh_content(interaction)

    async def _on_character_level_up(self, interaction: discord.Interaction):
        new_level = self.character.level + 1
        min_xp = self.ctx.server.get_xp_for_level(new_level)
        notes = f"Level up!: `{self.character.level}` -> `{new_level}`"

        if self.character.xp < min_xp:
            if await confirm_modal(
                interaction,
                (
                    f"`{self.character.name}` only has `{self.character.xp}` xp. Which is less than the defined `{min_xp}` for level {new_level}.\n\n"
                    f"Submitting this level up will automatically adjust the character xp to `{min_xp}`"
                    "Are you sure you wish to level this character up?"
                 )
            ):
                notes += f"\nXP Adjustment: `{self.character.xp}` -> {min_xp}"
                self.character.xp = min_xp
                
            else:
                return await self.refresh_content(interaction)
            
        self.character.level += 1

        await StewardLog.create(
            self.bot,
            self.ctx.author,
            self.player,
            LogEvent.level_up,
            character=self.character,
            notes=notes
        )

        await self.refresh_content(interaction)

    
    async def _on_character_inactivate(self, interaction: discord.Interaction):
        if await confirm_modal(
            interaction,
            f"Are you sure you wish to inactivate this character?"
        ):
            self.character.active = False

            await StewardLog.create(
                self.bot,
                self.ctx.author,
                self.player,
                LogEvent.edit_character,
                character=self.character,
                notes="Inactivating character"
            )

            # Refresh player
            self.player = await Player.get_or_create(self.bot.db, self.player)

        await self.refresh_content(interaction)
        
class NewCharacterView(BaseInfoView):
    new_character: Character = None
    reroll_character: Character = None
    application_type: ApplicationType

    def __init__(self, bot: StewardBot, ctx: StewardContext, player: Player, **kwargs):
        self.owner = ctx.author
        self.bot = bot
        self.ctx = ctx
        self.player = player
        self.staff = kwargs.get("staff", False)
        self.admin = kwargs.get("admin", False)
        self.delete_on_timeout = kwargs.get("delete", False)
        self.new_character = Character(
            self.bot.db, 
            player_id=self.player.id, 
            guild_id=self.player.guild.id,
            primary_character=True if not self.player.active_characters else False
        )
        self.reroll_character = kwargs.get("reroll_character")
        self.application_type = kwargs.get("application_type")

        content = []
        separator = ui.Separator()

        container = ui.Container(
            ui.Section(
                ui.TextDisplay(f"{self.player.mention}"),
                accessory=ui.Thumbnail(
                    url=f"{self.player.avatar.url}"
                )
            ),
            separator,
            ui.TextDisplay(
                f"**Name**: {self.new_character.name or '`None`'}\n"
                f"**Level**: {self.new_character.level}\n"
                f"**Species**: {self.new_character.species_str or '`None`'}\n"
                f"**Class**: {self.new_character.class_str or '`None`'}\n"
                f"**{self.ctx.server.currency_str}**: {self.new_character.currency:,2f}"
            )
        )

        content.append(container)

        # Application Type
        for type in ApplicationType:
            if (
                type == ApplicationType.new
                and (
                    not self.player.active_characters
                    or len(self.player.active_characters) < self.ctx.server.max_characters(self.player)
                )
            ):
                pass


        #

    async def _on_cancel(self, interaction: discord.Interaction):
        await self.defer_to(PlayerInfoView, interaction)
        
    