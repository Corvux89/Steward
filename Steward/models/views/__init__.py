from typing import Type
import discord
import discord.ui as ui

from Steward.models.embeds import ErrorEmbed
from Steward.models.objects.player import Player
from Steward.utils.discordUtils import try_delete

class StewardView(ui.DesignerView):
    __copy_attrs__ = []
    owner: Player
    delete_on_timeout: bool = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner.id:
            return True
        return False
    
    async def on_error(self, error, item, interaction):
        if hasattr(self, "bot"):
            await self.bot.error_handling(interaction, error)
        else:
            await interaction.channel.send(embed=ErrorEmbed(error))

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
            self.remove_all_buttons_and_action_rows()
            await self.message.edit(view=self)

            if self.delete_on_timeout:
                await try_delete(message)
                

    @classmethod
    def from_menu(cls, other: "StewardView") -> "StewardView":   
        init_kwargs = {}
        for attr in getattr(cls, '__copy_attrs__', []):
            value = getattr(other, attr, None)
            if value is not None:
                init_kwargs[attr] = value
        
        inst = cls(**init_kwargs)
        inst.message = other.message
        
        if hasattr(other, 'delete_on_timeout'):
            inst.delete_on_timeout = other.delete_on_timeout
        if hasattr(other, 'timeout') and other.timeout is not None:
            inst.timeout = other.timeout

        return inst

    @staticmethod
    async def prompt_modal(modal: ui.DesignerModal, interaction: discord.Interaction) -> ui.DesignerModal:
        await interaction.response.send_modal(modal)
        await modal.wait()

        return modal

    async def defer_to(self, view_type: Type["StewardView"], interaction: discord.Interaction, stop=True):
        view = view_type.from_menu(self)

        if stop:
            self.stop()

        if interaction.response.is_done():
            await interaction.edit_original_message(view=view)
        else:
            await interaction.response.edit_message(view=view)


    def _extract_text_from_section(self, section: ui.Section) -> ui.TextDisplay | None:
        for item in section.items:
            if isinstance(item, ui.TextDisplay):
                return item
        return None
    
    def _has_button_accessory(self, section: ui.Section) -> bool:
        return hasattr(section, 'accessory') and isinstance(section.accessory, ui.Button)
    
    def _process_sections_in_parent(self, parent, parent_items):
        replacements = []
        for item in parent_items:
            if isinstance(item, ui.Section) and self._has_button_accessory(item):
                text_display = self._extract_text_from_section(item)
                if text_display:
                    replacements.append((parent, item, text_display))
        return replacements

    def remove_all_buttons_and_action_rows(self):
        action_rows_to_remove = []
        replacements = []
        
        # Process view children
        for child in self.children:
            if isinstance(child, ui.ActionRow):
                action_rows_to_remove.append(child)
            elif isinstance(child, ui.Section):
                replacements.extend(self._process_sections_in_parent(self, [child]))
            elif isinstance(child, ui.Container):
                replacements.extend(self._process_sections_in_parent(child, child.items))
        
        # Remove action rows from view
        for action_row in action_rows_to_remove:
            self.remove_item(action_row)
        
        # Apply all section replacements
        for parent, section, text_display in replacements:
            if parent is not None and section.parent is not None:
                parent.remove_item(section)
                parent.add_item(text_display)

    async def refresh_content(self, interaction: discord.Interaction):
        view = self.from_menu(self)

        if interaction.response.is_done():
            await interaction.edit_original_message(view=view)
        else:
            await interaction.response.edit_message(view=view)


            