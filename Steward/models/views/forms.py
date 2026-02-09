import discord.ui as ui
import discord

from Steward.bot import StewardBot, StewardContext
from Steward.models.objects.character import Character
from Steward.models.objects.form import FormTemplate, Application
from Steward.models.objects.player import Player
from Steward.models.views import StewardView
from Steward.models.modals import get_field_value_modal
from Steward.utils.viewUitils import get_character_header, get_player_header


class BasicFormView(StewardView):
    __copy_attrs__ = ['bot', 'ctx', 'player', 'template', 'application', 'character']

    bot: StewardBot
    ctx: StewardContext
    player: Player
    template: FormTemplate
    application: Application
    character: Character


class FormView(BasicFormView):
    def __init__(self, bot: StewardBot, ctx: StewardContext, template: FormTemplate, **kwargs):
        super().__init__()
        self.owner = ctx.author
        self.bot = bot
        self.ctx = ctx
        self.player = ctx.player

        self.character = kwargs.get('character')
        self.template = template
        
        existing_app = kwargs.get('application')
        if existing_app:
            self.application = existing_app
        else:
            self.application = Application(
                bot.db,
                guild_id=ctx.guild.id,
                player_id=ctx.author.id,
                character_id=self.character.id if self.character else None,
                template_name=template.name,
                data={},
                template=template,
                player=self.player,
                character=self.character
            )

    async def get_message_content(self) -> dict:        
        if self.template.character_specific and self.character:
            header = get_character_header(self.player, self.character)
        else:
            header = get_player_header(self.player)

        content_lines = [
            "## Form: " + self.template.name,
            "Fill out the fields below by clicking the buttons.",
            ""
        ]

        if self.application.data:
            content_lines.append("**Current Values:**")
            for field in self.template.content:
                label = field.get('label', '')
                value = self.application.data.get(label, '_`Not set`_')
                content_lines.append(f"• **{label}**: {value}")
        else:
            content_lines.append("_No fields filled yet._")

        content_text = '\n'.join(content_lines)

        content = [
            ui.Container(
                header,
                ui.Separator(),
                ui.TextDisplay(content=content_text)
            )
        ]

        # Add field buttons in ActionRows (max 5 buttons per row)
        if self.template.content:
            current_row = []
            for field in self.template.content:
                label = field.get('label', 'Field')
                key = field.get('key', label)
                required = field.get('required', False)
                
                # Truncate label for button if too long
                button_label = label[:80] if len(label) <= 80 else label[:77] + "..."
                
                # Check if field has a value
                has_value = label in self.application.data and self.application.data[label]
                button_style = discord.ButtonStyle.primary if has_value else discord.ButtonStyle.secondary
                
                button = ui.Button(
                    label=button_label,
                    style=button_style,
                    custom_id=f"field_{key}"
                )
                button.callback = self._create_field_callback(field)
                current_row.append(button)
                
                # Add ActionRow when we have 5 buttons or it's the last field
                if len(current_row) == 5:
                    content.append(ui.ActionRow(*current_row))
                    current_row = []
            
            # Add remaining buttons
            if current_row:
                content.append(ui.ActionRow(*current_row))

        # Add submit and cancel buttons in final row
        submit_button = ui.Button(
            label="Submit Form",
            style=discord.ButtonStyle.success,
            custom_id="submit_form"
        )
        submit_button.callback = self._submit_form

        cancel_button = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="cancel_form"
        )
        cancel_button.callback = self._cancel_form
        
        content.append(ui.ActionRow(submit_button, cancel_button))

        return {"content": content}

    def _create_field_callback(self, field: dict):
        async def field_callback(interaction: discord.Interaction):
            label = field.get('label', '')
            current_value = self.application.data.get(label, "")
            
            value = await get_field_value_modal(interaction, field, current_value)
            
            if value is not None:
                self.application.data[label] = value
                self.application = await self.application.upsert()
            
            await self.refresh_content(interaction)
        
        return field_callback

    async def _submit_form(self, interaction: discord.Interaction):
        # Validation
        missing_fields = []
        if self.template.content:
            for field in self.template.content:
                if field.get('required', False):
                    label = field.get('label', '')
                    if not self.application.data.get(label):
                        missing_fields.append(label)
        
        if missing_fields:
            await interaction.response.send_message(
                f"❌ Please fill out the following required fields:\n" + 
                "\n".join(f"• {field}" for field in missing_fields),
                ephemeral=True
            )
            return
        
        # Mark as submitted and save
        self.application.status = 'submitted'
        self.application = await self.application.upsert()
        
        # Dispatch event 
        self.bot.dispatch("new_application", self.application)
        
        await interaction.response.send_message(
            "✅ Form submitted successfully!",
            ephemeral=True
        )
        
        await self.on_timeout()

    async def _cancel_form(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Form cancelled.",
            ephemeral=True
        )
        await self.on_timeout()

    async def refresh_content(self, interaction: discord.Interaction):
        """Refresh the form display."""
        new_view = FormView(self.bot, self.ctx, self.template, character=self.character, application=self.application)
        new_view.owner = self.owner
        
        content = await new_view.get_message_content()
        super(FormView, new_view).__init__(*content["content"])
        
        # Update the message with the new view
        await interaction.edit(view=new_view)

    async def send(self):
        content = await self.get_message_content()
        super(FormView, self).__init__(*content["content"])
        await self.ctx.respond(view=self, allowed_mentions=discord.AllowedMentions(users=False, roles=False))