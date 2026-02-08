from typing import Optional, Union
import discord
import discord.ui as ui


def _extract_modal_value(interaction, custom_id: str) -> Optional[str]:
    data = getattr(interaction, "data", None) or {}
    components = data.get("components") or []
    for row in components:
        for component in row.get("components", []):
            if component.get("custom_id") == custom_id:
                return component.get("value")
    return None

class PromptModal(ui.DesignerModal):
    value: Union[str, int] = None
    integer: bool = False

    def __init__(
            self, 
            label: str,
            current_value: str,
            title: str,
            **kwargs
        ):
        """
        Initialize a modal with a labeled input field or select menu.
        Args:
            label (str): The label text to display above the input field or select.
            current_value (str): The initial value to populate in the input field or select.
            title (str): The title of the modal dialog.
            **kwargs: Additional keyword arguments:
                - placeholder (str, optional): Placeholder text for the input field. Defaults to label.
                - length (int, optional): Maximum character length for the input. Defaults to 100.
                - integer (bool, optional): Whether the input should be treated as an integer. Defaults to False.
                - items (list, optional): List of items to display in a select menu. If provided, creates a Select instead of InputText.
                - required (bool, optional): Whether the input should be required. Defaults to False.
        """

        placeholder = kwargs.get('placeholder', label)
        max_length = kwargs.get("length", 100)
        self.integer = kwargs.get("integer", False)
        required = kwargs.get("required", False)
        items = kwargs.get("items")

        if items:
            # Create select menu from items
            options = [
                discord.SelectOption(label=str(item), value=str(item))
                for item in items
            ]
            
            super().__init__(
                ui.Label(
                    label,
                    ui.Select(
                        placeholder=placeholder,
                        options=options,
                        custom_id="value",
                        required=required
                    )
                ),
                title=title
            )
        else:
            # Create text input
            safe_max_length = min(max_length, 4000)
            safe_placeholder = str(placeholder).replace("\r", " ").replace("\n", " ")
            input_kwargs = {
                "placeholder": safe_placeholder,
                "max_length": safe_max_length,
                "custom_id": "value",
                "required": required,
            }

            if current_value is not None:
                safe_value = str(current_value).replace("\r", " ").replace("\n", " ")
                if safe_value:
                    input_kwargs["value"] = safe_value[:safe_max_length]

            super().__init__(
                ui.Label(
                    label,
                    ui.InputText(**input_kwargs)
                ),
                title=title
            )

    async def callback(self, interaction):
        item = self.get_item("value")
        if hasattr(item, 'values'):
            # Select menu
            value = item.values[0] if item.values else None
        else:
            # InputText
            value = item.value
            if value is None:
                value = _extract_modal_value(interaction, "value")
            
        try:
            if self.integer == True and value:
                self.value = int(value)
            else:
                self.value = value
        except:
            self.value = None

        await interaction.response.defer()
        self.stop()

async def get_value_modal(
        ctx: Union[discord.ApplicationContext, discord.Interaction],
        label: str,
        current_value: str = "",
        title: str = "Input a value",
        **kwargs
    ) -> Optional[Union[int, str]]:
    """
    Display a modal dialog to get a value from the user.
    Args:
        ctx (Union[discord.ApplicationContext, discord.Interaction]): The context or interaction object to send the modal through.
        label (str): The label text to display in the modal input field or select.
        current_value (str, optional): The pre-filled value in the input field or select. Defaults to "".
        title (str, optional): The title of the modal dialog. Defaults to "Input a value".
        **kwargs: Additional keyword arguments:
                - placeholder (str, optional): Placeholder text for the input field. Defaults to label.
                - length (int, optional): Maximum character length for the input. Defaults to 100.
                - integer (bool, optional): Whether the input should be treated as an integer. Defaults to False.
                - items (list, optional): List of items to display in a select menu. If provided, creates a Select instead of InputText.
                - required (bool, optional): Whether the input should be required. Defaults to False
    Returns:
        Union[int, str, None]: The value entered by the user or selected from the list. Returns an integer if 'integer' kwarg is True,
                                otherwise returns a string. Returns None if no value was provided.
    Raises:
        ValueError: If 'integer' is True and the input cannot be converted to an integer.
    """
    
    modal = PromptModal(label, current_value, title, **kwargs)
    integer = kwargs.get('integer', False)
    if hasattr(ctx, "send_modal"):
        await ctx.send_modal(modal)
    else:
        await ctx.response.send_modal(modal)

    await modal.wait()
    value = getattr(modal, "value", None)
    
    if integer and value:
        return int(value)
    
    return value


class CharacterSelectModal(ui.DesignerModal):
    """Modal for selecting a character from a list."""
    selected_character: Optional[str] = None

    def __init__(self, characters: list, title: str = "Select Character"):
        """
        Initialize a modal for character selection.
        
        Args:
            characters (list): List of Character objects to choose from
            title (str): The title of the modal dialog
        """
        # Create options for the select menu
        options = [
            discord.SelectOption(label=char.name, value=char.name)
            for char in characters
        ]
        
        super().__init__(
            ui.Label(
                "Character",
                ui.Select(
                    placeholder="Choose a character...",
                    options=options,
                    custom_id="character_select"
                )
            ),
            title=title
        )

    async def callback(self, interaction):
        selected = self.get_item("character_select").values
        if selected:
            self.selected_character = selected[0]
        await interaction.response.defer()
        self.stop()


async def get_character_select_modal(
        ctx: Union[discord.ApplicationContext, discord.Interaction],
        characters: list,
        title: str = "Select Character"
    ) -> Optional[str]:
    """
    Display a modal dialog to select a character.
    
    Args:
        ctx: The context or interaction object to send the modal through
        characters: List of Character objects to choose from
        title: The title of the modal dialog
    
    Returns:
        The name of the selected character, or None if no selection was made
    """
    modal = CharacterSelectModal(characters, title)
    
    if hasattr(ctx, "send_modal"):
        await ctx.send_modal(modal)
    else:
        await ctx.response.send_modal(modal)

    await modal.wait()
    
    return getattr(modal, "selected_character", None)


class DynamicFieldModal(ui.DesignerModal):
    """Modal for capturing a single field value in a dynamic form."""
    value: Optional[str] = None

    def __init__(
            self,
            field: dict,
            current_value: str = ""
        ):
        """
        Initialize a modal for a dynamic form field.
        
        Args:
            field (dict): Field configuration with keys:
                - label (str): The field label
                - key (str): The field key/identifier
                - style (str): 'short' or 'long' text input
                - required (bool): Whether the field is required
                - max_length (int): Maximum character length
                - placeholder (str, optional): Placeholder text
            current_value (str): The current value of the field
        """
        label = field.get('label', 'Value')
        placeholder = field.get('placeholder', '')
        max_length = field.get('max_length', 1000)
        required = field.get('required', False)
        style = field.get('style', 'short')
        description = field.get('description')

        content = []

        # Input field
        text_style = discord.InputTextStyle.long if style == 'long' else discord.InputTextStyle.short
        safe_max_length = max(1, min(int(max_length), 4000))
        safe_value = None if current_value is None else str(current_value)
        safe_label = str(label)[:45]
        placeholder_base = placeholder or label
        if not placeholder_base and description:
            placeholder_base = description
        safe_placeholder = str(placeholder_base)
        safe_value = safe_value
        if text_style == discord.InputTextStyle.short:
            safe_placeholder = safe_placeholder.replace("\r", " ").replace("\n", " ")
            if safe_value is not None:
                safe_value = safe_value.replace("\r", " ").replace("\n", " ")
        safe_placeholder = safe_placeholder[:100]
        input_kwargs = {
            "placeholder": safe_placeholder,
            "max_length": safe_max_length,
            "custom_id": "field_value",
            "required": required,
            "style": text_style,
        }

        if safe_value:
            input_kwargs["value"] = safe_value[:safe_max_length]

        content.append(
            ui.Label(
                safe_label,
                ui.InputText(**input_kwargs)
            )
        )

        super().__init__(
            *content,
            title=f"Enter {label}"[:45]  # Discord title length limit
        )

    async def callback(self, interaction):
        item = self.get_item("field_value")
        value = getattr(item, "value", None)
        if value is None:
            value = _extract_modal_value(interaction, "field_value")
        self.value = value
        try:
            await interaction.response.defer()
        except:
            pass
        self.stop()


async def get_field_value_modal(
        ctx: Union[discord.ApplicationContext, discord.Interaction],
        field: dict,
        current_value: str = ""
    ) -> Optional[str]:
    """
    Display a modal dialog to get a field value from the user.
    
    Args:
        ctx: The context or interaction object to send the modal through
        field: Field configuration dictionary
        current_value: The pre-filled value in the input field
    
    Returns:
        The value entered by the user, or None if no value was provided
    """
    modal = DynamicFieldModal(field, current_value)
    
    if hasattr(ctx, "send_modal"):
        await ctx.send_modal(modal)
    else:
        await ctx.response.send_modal(modal)

    await modal.wait()
    
    return getattr(modal, "value", None)
