import logging
import discord
import discord.ui as ui

from Steward.bot import StewardBot, StewardApplicationContext
from Steward.models.modals.player import NewCharacterModal, PlayerInformationModal
from Steward.models.modals import get_value_modal
from Steward.models.objects.character import Character
from Steward.models.objects.enum import ApplicationType, LogEvent, RuleTrigger
from Steward.models.objects.log import StewardLog
from Steward.models.objects.player import Player
from Steward.models.views import StewardView, confirm_view
from Steward.utils.discordUtils import chunk_text, try_delete
from Steward.utils.viewUitils import get_character_header, get_character_info_sections, get_character_select_option, get_player_header
from constants import EDIT_EMOJI

log = logging.getLogger(__name__)


class BaseInfoView(StewardView):
    __copy_attrs__ = [
        'bot', 'ctx', 'player', 'staff', 
        'character', 'admin', 'application_type', 'new_character', 
        'reroll_character'
    ]

    bot: StewardBot
    ctx: StewardApplicationContext
    player: Player
    staff: bool
    admin: bool
    character: Character
    delete_on_timeout: bool

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

            try:
                await self.message.edit(view=view)
            except:
                pass

            if self.delete_on_timeout:
                await try_delete(message)


class PlayerInfoView(BaseInfoView):
    def __init__(self, bot: StewardBot, ctx: StewardApplicationContext, player: Player, **kwargs):
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
            get_player_header(self.player),
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

            
            new_character_button = ui.Button(
                label="New Character",
                style=discord.ButtonStyle.green,
                custom_id="new_character"
            )
            new_character_button.callback = self._on_new_character_button
            row_1_buttons.append(new_character_button)

            exit_button = ui.Button(
                label="Quit",
                style=discord.ButtonStyle.red
            )
            exit_button.callback = self.timeout_callback
            row_1_buttons.append(exit_button)

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
        modal = PlayerInformationModal(self.bot, self.player, self.admin)
        await self.prompt_modal(modal, interaction)

        await self.refresh_content(interaction)

    async def _on_new_character_button(self, interaction: discord.Interaction):
        await self.defer_to(NewCharacterView, interaction)

class CharacterInfoView(BaseInfoView):
    def __init__(self, bot: StewardBot, ctx: StewardApplicationContext, player: Player, character: Character, **kwargs):
        self.owner = ctx.author
        self.bot = bot
        self.ctx = ctx
        self.player = player
        self.character = character
        self.staff = kwargs.get("staff", False)
        self.admin = kwargs.get("admin", False)
        self.delete_on_timeout = kwargs.get("delete", False)
        
        content = self._build_content()
        super().__init__(*content)
    
    def _build_content(self) -> list:
        """Build and return the view content."""
        content = []
        separator = ui.Separator(divider=True)
        
        # Header section
        container = ui.Container(
            get_character_header(self.player, self.character),
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
        nickname_display = ui.TextDisplay(f"**Nickname**: {self.character.nickname or '`None`'}")
        
        if self.character.player_id == self.ctx.author.id:
            edit_nickname_button = ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=EDIT_EMOJI[0],
                custom_id="edit_character_nickname",
            )
            edit_nickname_button.callback = self._on_edit_character_nickname
            container.add_item(ui.Section(nickname_display, accessory=edit_nickname_button))
        else:
            container.add_item(nickname_display)
    
    def _add_currency_section(self, container: ui.Container):
        currency_display = ui.TextDisplay(
            f"**{self.ctx.server.currency_str}**: {self.character.currency:,}\n"
        )
    
        if self.staff:
            edit_currency_button = ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=EDIT_EMOJI[0],
                custom_id="edit_character_currency"
            )
            edit_currency_button.callback = self._on_edit_character_currency
            container.add_item(ui.Section(currency_display, accessory=edit_currency_button))
        else:
            container.add_item(currency_display)

        limited_currency_display = ui.TextDisplay(
            f"**Limited {self.ctx.server.currency_str}**: {self.character.limited_currency:,} / {self.ctx.server.currency_limit(self.player, self.character)}"
        )

        if self.staff:
            edit_limited_currency_button = ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=EDIT_EMOJI[0],
                custom_id="edit_character_limited_currency"
            )
            edit_limited_currency_button.callback = self._on_edit_character_limited_currency
            container.add_item(ui.Section(limited_currency_display, accessory=edit_limited_currency_button))
        else:
            container.add_item(limited_currency_display)
    
    def _add_xp_section(self, container: ui.Container):
        xp_level = self.ctx.server.get_level_for_xp(self.character.xp)
        xp_display = ui.TextDisplay(
            f"**XP**: {self.character.xp:,} (Level {xp_level}{' eligible' if xp_level > self.character.level else ''})"
        )
        
        if self.staff:
            edit_xp_button = ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=EDIT_EMOJI[0],
                custom_id="edit_character_xp"
            )
            edit_xp_button.callback = self._on_edit_character_xp
            container.add_item(ui.Section(xp_display, accessory=edit_xp_button))
        else:
            container.add_item(xp_display)

        limited_xp_display = ui.TextDisplay(
            f"**Limited XP**: {self.character.limited_xp:,} / {self.ctx.server.xp_limit(self.player, self.character)}"
        )

        if self.staff:
            edit_limited_xp_button = ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=EDIT_EMOJI[0],
                custom_id="edit_character_limited_xp"
            )
            edit_limited_xp_button.callback = self._on_edit_character_limited_xp
            container.add_item(ui.Section(limited_xp_display, accessory=edit_limited_xp_button))
        else:
            container.add_item(limited_xp_display)
    
    def _add_activity_section(self, container: ui.Container):
        if self.ctx.server.activity_points:
            activity_point = self.ctx.server.get_activitypoint_for_points(self.character.activity_points)
            activity_level = 'Level 0' if not activity_point else f'Level {activity_point.level}'
            activity_display = ui.TextDisplay(    
                f"**Activity Points**: {self.character.activity_points:,} ({activity_level})"
            )

            if self.admin:
                edit_ap_button = ui.Button(
                    style=discord.ButtonStyle.secondary,
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

            activity_button = ui.Button(
                label="Character Activity Settings",
                style=discord.ButtonStyle.blurple,
                custom_id="activity_char"
            )
            activity_button.callback = self._on_character_activity
            buttons.append(activity_button)

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

        exit_button = ui.Button(
                label="Quit",
                style=discord.ButtonStyle.red
            )
        exit_button.callback = self.timeout_callback
        buttons.append(exit_button)

        return buttons
    
    async def _on_char_select(self, interaction: discord.Interaction):
        char = self.get_item("char_select").values[0]

        if char == "def":
            return await self.defer_to(PlayerInfoView, interaction)
            

        character = next(
            (c for c in self.player.active_characters if str(c.id) == char),
            None
        )
        self.character = character
        
        await self.defer_to(CharacterInfoView, interaction)

    async def _on_edit_character_nickname(self, interaction: discord.Interaction):
        old_nick = self.character.nickname if self.character.nickname and self.character.nickname != '' else ' '
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

    async def _on_character_activity(self, interaction: discord.Interaction):
        await self.defer_to(CharacterActivityView, interaction)

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

    async def _on_edit_character_limited_currency(self, interaction: discord.Interaction):
        old_limited_currency = self.character.limited_currency
        new_limited_currency = await get_value_modal(
            interaction,
            f"Limited {self.ctx.server.currency_str}",
            str(old_limited_currency),
            f"Character limited {self.ctx.server.currency_str}",
            integer=True,
            length=100
        )

        if new_limited_currency is not None and old_limited_currency != new_limited_currency:
            difference = new_limited_currency - old_limited_currency
            self.character.limited_currency = new_limited_currency

            await StewardLog.create(
                self.bot,
                self.ctx.author,
                self.player,
                LogEvent.edit_character,
                character=self.character,
                notes=f"Limited Currency Update: `{old_limited_currency}` -> `{new_limited_currency}` ({difference})"
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

    async def _on_edit_character_limited_xp(self, interaction: discord.Interaction):
        old_limited_xp = self.character.limited_xp
        new_limited_xp = await get_value_modal(
            interaction,
            "Limited XP",
            str(old_limited_xp),
            "Character Limited XP",
            integer=True,
            length=10
        )

        if new_limited_xp is not None and old_limited_xp != new_limited_xp:
            difference = new_limited_xp - old_limited_xp
            self.character.limited_xp = new_limited_xp

            await StewardLog.create(
                self.bot,
                self.ctx.author,
                self.player,
                LogEvent.edit_character,
                character=self.character,
                notes=f"Limited XP Update: `{old_limited_xp}` -> `{new_limited_xp}` ({difference})"
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
            if await confirm_view(
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
            if await confirm_view(
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

        log = await StewardLog.create(
            self.bot,
            self.ctx.author,
            self.player,
            LogEvent.level_up,
            character=self.character,
            notes=notes
        )

        self.bot.dispatch(RuleTrigger.level_up.name, interaction, self.character, log)

        await self.refresh_content(interaction)

    
    async def _on_character_inactivate(self, interaction: discord.Interaction):
        if await confirm_view(
            interaction,
            f"Are you sure you wish to inactivate this character?"
        ):
            self.character.active = False

            log = await StewardLog.create(
                self.bot,
                self.ctx.author,
                self.player,
                LogEvent.edit_character,
                character=self.character,
                notes="Inactivating character"
            )

            # Refresh player
            self.player = await Player.get_or_create(self.bot.db, self.player)

            self.bot.dispatch(RuleTrigger.inactivate_character.name, interaction, self.character, log)
            self.character = None

        await self.defer_to(PlayerInfoView, interaction)
        
class NewCharacterView(BaseInfoView):
    new_character: Character = None
    application_type: ApplicationType
    reroll_character: Character

    def __init__(self, bot: StewardBot, ctx: StewardApplicationContext, player: Player, **kwargs):
        self.owner = ctx.author
        self.bot = bot
        self.ctx = ctx
        self.player = player
        self.staff = kwargs.get("staff", False)
        self.admin = kwargs.get("admin", False)
        self.delete_on_timeout = kwargs.get("delete", False)
        self.application_type = kwargs.get("application_type")
        self.new_character = kwargs.get(
            "new_character", 
            Character(
                self.bot.db, 
                player_id=self.player.id, 
                guild_id=self.player.guild.id,
                primary_character=True if not self.player.active_characters else False
            )
        )
        self.reroll_character = kwargs.get("reroll_character")

        content = []
        separator = ui.Separator()

        container = ui.Container(
            get_player_header(self.player),
            separator,
            ui.TextDisplay(
                f"**Name**: {self.new_character.name or '`None`'}\n"
                f"**Level**: {self.new_character.level}\n"
                f"**Species**: {self.new_character.species_str or '`None`'}\n"
                f"**Class**: {self.new_character.class_str or '`None`'}\n"
                f"**{self.ctx.server.currency_str}**: {self.new_character.currency:,.2f}"
            )
        )

        content.append(container)
        content.append(ui.ActionRow(
            self._add_button_row_1()
        ))

        if self.application_type and self.application_type != ApplicationType.new:
            content.append(ui.ActionRow(
                self._add_button_row_2()
            ))

        
        content.append(
            ui.ActionRow(
                *self._add_button_row_3()
            )
        )

        super().__init__(*content)
    
    def _add_button_row_1(self):
        options = []

        for type in ApplicationType:
            match type:
                case ApplicationType.new:
                    default = True if not self.player.active_characters or self.application_type and self.application_type == type or len(self.player.active_characters) < self.ctx.server.max_characters(self.player) else False
                    if len(self.player.active_characters) == 0 or len(self.player.active_characters) < self.ctx.server.max_characters(self.player):
                        options.append(
                            discord.SelectOption(
                                label=type.value,
                                value=type.name,
                                default=True
                            )
                        )
                case ApplicationType.level:
                    pass

                case _:
                    if self.player.active_characters:
                        options.append(
                            discord.SelectOption(
                                label=type.value,
                                value=type.name,
                                default=True if self.application_type and self.application_type == type else False
                            )
                        )

        self.application_type = ApplicationType.from_string(options[0].value)
        reroll_select = ui.Select(
            placeholder="Character Creation Type",
            custom_id="application_type",
            options=options
        )
        reroll_select.callback = self._on_application_type_select

        return reroll_select
    
    def _add_button_row_2(self):
        character_select = get_character_select_option(self.player, self.reroll_character, self._on_reroll_character_select, default="Select a character to reroll")
        return character_select

    def _add_button_row_3(self):
        buttons = []

        enabled = (
            self.new_character 
            and self.new_character.name != "" 
            and self.new_character.species_str != ""
            and self.new_character.class_str != ""
            and (
                self.application_type
                and (
                    self.application_type == ApplicationType.new
                    or self.reroll_character
                )
            )
        )

        # Create Character
        create_button = ui.Button(
            label="Create Character",
            style=discord.ButtonStyle.green,
            disabled=True if not enabled else False,
        )
        create_button.callback = self._on_create_button
        buttons.append(create_button)

        # Character Information
        info_button = ui.Button(
            label="Character Information",
            style=discord.ButtonStyle.blurple
        )
        info_button.callback = self._on_info_button
        buttons.append(info_button)

        # Cancel
        cancel_button = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.red
        )
        cancel_button.callback = self._on_cancel_button

        buttons.append(cancel_button)

        return buttons

    async def _on_reroll_character_select(self, interaction: discord.Interaction):
        char = self.get_item("char_select").values[0]

        if char == "def":
            self.reroll_character = None
        else:
            character = next(
                (c for c in self.player.active_characters if str(c.id) == char),
                None
            )
            self.reroll_character = character

        await self.refresh_content(interaction)

    async def _on_application_type_select(self, interaction: discord.Interaction):
        type = self.get_item("application_type").values[0]
        self.reroll_character = None
        self.application_type = ApplicationType.from_string(type)

        await self.refresh_content(interaction)

    async def _on_cancel_button(self, interaction: discord.Interaction):
        await self.defer_to(PlayerInfoView, interaction)

    async def _on_info_button(self, interaction: discord.Interaction):
        modal = NewCharacterModal(self.new_character, self.ctx.server)
        await self.prompt_modal(modal, interaction)

        await self.refresh_content(interaction)

    async def _on_create_button(self, interaction: discord.Interaction):
        if self.application_type != ApplicationType.new:
            self.reroll_character.active = False
            reroll_log = await StewardLog.create(
                self.ctx.bot,
                self.ctx.author,
                self.player,
                LogEvent.edit_character,
                character=self.reroll_character,
                notes=f"str(self.application_type.value) -> Inactivating Character"
            )
            await self.bot.dispatch(RuleTrigger.inactivate_character.name, interaction, self.reroll_character, reroll_log)

        new_log = await StewardLog.create(
            self.ctx.bot,
            self.ctx.author,
            self.player,
            LogEvent.new_character,
            character=self.new_character,
            notes=f"New character!{f' Rerolled from {self.reroll_character.name} [{self.reroll_character.id}]' if self.reroll_character else ''}"
        )

        self.player = await Player.get_or_create(self.bot.db, self.player)
        self.bot.dispatch(RuleTrigger.new_character.name, interaction, self.new_character, new_log)

        await self.defer_to(PlayerInfoView, interaction)

class CharacterActivityView(BaseInfoView):
    def __init__(self, bot: StewardBot, ctx: StewardApplicationContext, player: Player, character: Character, **kwargs):
        self.owner = ctx.author
        self.bot = bot
        self.ctx = ctx
        self.player = player
        self.character = character
        self.staff = kwargs.get("staff", False)
        self.admin = kwargs.get("admin", False)
        self.delete_on_timeout = kwargs.get("delete", False)
        
        content = self._build_content()
        super().__init__(*content)
        
    def _build_content(self) -> list:
        content = []
        separator = ui.Separator()

        container = ui.Container(
            get_character_header(self.player, self.character),
            separator
        )

        self._add_channel_section(container) 

        content.append(container)

        character_select = get_character_select_option(self.player, self.character, self._on_char_select)
        content.append(ui.ActionRow(character_select))
        
        self._add_action_row_2(content)

        return content

    def _add_channel_section(self, container):
        channels = [
            self.ctx.server.get_channel_or_thread(c).mention
            for c in self.character.channels
            if self.ctx.server.get_channel_or_thread(c)
        ]

        text = "\n".join(channels)
        chunks = chunk_text(text)

        for chunk in chunks:
            container.add_item(
                ui.TextDisplay(
                    f"**Channel Defaults**:\n"
                    f"{chunk}"
                )
            )

    def _add_action_row_2(self, content):
        buttons = []
        if self.ctx.author.id == self.player.id:
            clear_channel_button = ui.Button(
                label="Clear channel overrides",
                style=discord.ButtonStyle.red,
            )
            clear_channel_button.callback = self._on_clear_channel
            buttons.append(clear_channel_button)

            primary_char = ui.Button(
                label="Set primary character",
                style=discord.ButtonStyle.green,
                disabled=True if self.character.primary_character else False
            )
            primary_char.callback = self._on_primary_character
            buttons.append(primary_char)

        back_button = ui.Button(
            label="Back"
        )
        back_button.callback = self._on_back
        buttons.append(back_button)

        content.append(
            ui.ActionRow(
                *buttons
            )
        )

    async def _on_clear_channel(self, interaction: discord.Interaction):
        if await confirm_view(
            self.ctx,
            f"Are you sure you want to clear all {len(self.character.channels)} channel overrides for this character?"
        ):
            self.character.channels = []
            await self.character.upsert()

        await self.refresh_content(interaction)

    async def _on_primary_character(self, interaction: discord.Interaction):
        for char in self.player.active_characters:
            if char.primary_character == True:
                char.primary_character = False
                await char.upsert()

        self.character.primary_character = True
        await self.character.upsert()

        await self.refresh_content(interaction)

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
        
        await self.defer_to(CharacterActivityView, interaction)

    async def _on_back(self, interaction: discord.Interaction):
        await self.defer_to(CharacterInfoView, interaction)
        
