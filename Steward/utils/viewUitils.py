from typing import Coroutine
import discord
import discord.ui as ui

from constants import EDIT_EMOJI

from ..models.objects.character import Character
from ..models.objects.servers import Server

from ..models.objects.player import Player

def get_character_select_option(player: Player, character: Character = None, callback: Coroutine = None, **kwargs) -> discord.SelectOption:
    default_label = kwargs.get("default", "Player Overview")

    char_list = [
        discord.SelectOption(
            label=default_label,
            default=True if not character else False,
            value="def"
        )
    ]

    for char in player.active_characters[:24]:
        char_list.append(
            discord.SelectOption(
                label=str(char.name),
                value=str(char.id),
                description=f"Level {char.level} - {char.species_str} {char.class_str}",
                default=True if character and char.id == character.id else False
            )
        )

    character_select = ui.Select(
        placeholder="Characters",
        custom_id="char_select",
        options=char_list
    )

    if callback:
        character_select.callback = callback

    return character_select

def get_character_sections(player: Player, server: Server, callback: Coroutine) -> list[ui.Section]:
    char_list = []

    for char in player.active_characters[:24]:
        char_button = ui.Button(
            style=discord.ButtonStyle.blurple,
            emoji=EDIT_EMOJI[0],
            custom_id=f"{char.id}"
        )
        char_button.callback = callback

        char_list.append(
            ui.Section(
                ui.TextDisplay(
                    f"**{char.name}{'*' if char.primary_character == True else ''}**\n"
                    f"-# Level {char.level}\n"
                    f"-# {char.species_str} | {char.class_str}\n"
                    f"-# {char.currency} {server.currency_str} | {char.xp} xp"
                ),
                accessory=char_button
            )
        )

    return char_list


