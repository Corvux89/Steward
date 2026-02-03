from typing import Optional, Type, Union
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

    async def timeout_callback(self, _: discord.Interaction):
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

    def remove_all_buttons_and_action_rows(self):
        """Remove all buttons and action rows, keeping only text displays"""
        # Build list of items to keep without modifying structure
        items_to_keep = []
        
        for child in list(self.children):
            if child is None or isinstance(child, (ui.ActionRow, ui.Button)):
                continue
            elif isinstance(child, ui.Section) and self._has_button_accessory(child):
                # Extract text display from section with button
                text_display = self._extract_text_from_section(child)
                if text_display:
                    items_to_keep.append(text_display)
            elif isinstance(child, ui.Container):
                # Build filtered container
                new_container = ui.Container()
                for item in list(child.items):
                    if item is None or isinstance(item, (ui.Button, ui.ActionRow)):
                        continue
                    elif isinstance(item, ui.Section) and self._has_button_accessory(item):
                        text_display = self._extract_text_from_section(item)
                        if text_display:
                            new_container.add_item(text_display)
                    else:
                        new_container.add_item(item)
                
                if len(new_container.items) > 0:
                    items_to_keep.append(new_container)
            else:
                # Keep other items as-is
                items_to_keep.append(child)
        
        # Clear all children from self
        self.clear_items()
        
        # Add the filtered items back
        for item in items_to_keep:
            if item is not None:
                self.add_item(item)

    async def refresh_content(self, interaction: discord.Interaction):
        view = self.from_menu(self)

        if interaction.response.is_done():
            await interaction.edit_original_message(view=view)
        else:
            await interaction.response.edit_message(view=view)


# Basic view for a basic prompt
class ConfirmView(ui.View):
    def __init__(self, user_id: int, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.confirm: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes_button(self, _: ui.Button, interaction: discord.Interaction):
        self.confirm = True
        await interaction.response.defer()
        self.stop()

    @ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no_button(self, _: ui.Button, interaction: discord.Interaction):
        self.confirm = False
        await interaction.response.defer()
        self.stop()

async def confirm_view(
        ctx: Union[discord.ApplicationContext, discord.Interaction],
        prompt: str,
        *,
        timeout: int = 30,
        ephemeral: bool = True
) -> Optional[bool]:
    view = ConfirmView(ctx.user.id if hasattr(ctx, "user") else ctx.author.id, timeout=timeout)
    message: Optional[discord.Message] = None

    if hasattr(ctx, "respond"):
        response = await ctx.respond(prompt, view=view, ephemeral=ephemeral)
        if isinstance(response, discord.Message):
            message = response
        elif hasattr(response, "message"):
            message = response.message
    else:
        await ctx.response.send_message(prompt, view=view, ephemeral=ephemeral)
        if hasattr(ctx, "original_response"):
            try:
                message = await ctx.original_response()
            except Exception:
                message = None

    await view.wait()
    if message:
        await try_delete(message)
    return view.confirm