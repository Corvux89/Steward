from typing import Optional, Union
import discord
import discord.ui as ui

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
        Initialize a modal with a labeled input field.
        Args:
            label (str): The label text to display above the input field.
            current_value (str): The initial value to populate in the input field.
            title (str): The title of the modal dialog.
            **kwargs: Additional keyword arguments:
                - placeholder (str, optional): Placeholder text for the input field. Defaults to label.
                - length (int, optional): Maximum character length for the input. Defaults to 100.
                - integer (bool, optional): Whether the input should be treated as an integer. Defaults to False.
        """

        placeholder = kwargs.get('placeholder', label)
        max_length = kwargs.get("length", 100)
        self.integer = kwargs.get("integer", False)
        required = kwargs.get("required", False)

        super().__init__(
            ui.Label(
                label,
                ui.InputText(
                    placeholder=placeholder,
                    max_length=max_length,
                    value=str(current_value),
                    custom_id="value",
                    required=required
                )
            ),
            title=title
        )

    async def callback(self, interaction):
        value = self.get_item("value").value
        try:
            if self.integer == True:
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
        label (str): The label text to display in the modal input field.
        current_value (str, optional): The pre-filled value in the input field. Defaults to "".
        title (str, optional): The title of the modal dialog. Defaults to "Input a value".
        **kwargs: Additional keyword arguments:
                - placeholder (str, optional): Placeholder text for the input field. Defaults to label.
                - length (int, optional): Maximum character length for the input. Defaults to 100.
                - integer (bool, optional): Whether the input should be treated as an integer. Defaults to False.
                - required (bool, optional): Whether the input should be required. Defaults to False
    Returns:
        Union[int, str, None]: The value entered by the user. Returns an integer if 'integer' kwarg is True,
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
    
    if integer:
        return int(value)
    
    return value

class ConfirmModal(ui.DesignerModal):
    confirm: bool = False
    
    def __init__(
            self,
            prompt: str,
            title: str,
    ):
        super().__init__(
            ui.TextDisplay(
                content=prompt
            ),
            title=title
        )

    async def callback(self, interaction):
        self.confirm = True
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self):
        self.confirm = False
        self.stop()

async def confirm_modal(
        ctx: Union[discord.ApplicationContext, discord.Interaction],
        prompt: str,
        title: str = "Confirm?"
) -> bool:
    modal = ConfirmModal(prompt, title)

    if hasattr(ctx, "send_modal"):
        await ctx.send_modal(modal)
    else:
        await ctx.response.send_modal(modal)

    await modal.wait()

    return modal.confirm

