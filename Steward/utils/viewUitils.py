from typing import Coroutine, Union
import discord
import discord.ui as ui

from Steward.models.objects.activity import Activity
from Steward.models.objects.request import Request
from constants import DENIED_EMOJI, EDIT_EMOJI

from ..models.objects.character import Character
from ..models.objects.servers import Server

from ..models.objects.player import Player

def get_player_header(player: Player):
    return ui.Section(
        ui.TextDisplay(f"{player.mention}"),
        accessory=ui.Thumbnail(
            url=f"{player.avatar.url}"
        )
    )

def get_character_header(player: Player, character: Character):
    return ui.Section(
        ui.TextDisplay(
            f"{character.name} ({player.mention}){'*' if character.primary_character == True else ''}\n"
            f"-# Level {character.level}\n"
            f"-# {character.species_str} {character.class_str}"
        ),
        accessory=ui.Thumbnail(
            url=character.avatar_url or player.avatar.url
        ),
    )

def get_character_select_option(player: Player, character: Character = None, callback: Coroutine = None, **kwargs) -> discord.SelectOption:
    default_label = kwargs.get("default", "Player Overview")
    enable_def = kwargs.get("enable_def", True)

    if enable_def == True:
        char_list = [
            discord.SelectOption(
                label=default_label,
                default=True if not character else False,
                value="def"
            )
        ]
    else:
        char_list = []

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

def get_activity_select_option(server: Server, activity: Activity = None, callback: Coroutine = None, **kwargs) -> discord.SelectOption:
    default_label = kwargs.get("default", "Select an Activity")
    enable_def = kwargs.get("enable_def", True)

    if enable_def == True:
        act_list = [
            discord.SelectOption(
                label=default_label,
                default=True if not activity else False,
                value="def"
            )
        ]
    else:
        act_list = []

    for act in server.activities:
        act_list.append(
            discord.SelectOption(
                label=str(act.name),
                value=str(act.name),
                default=True if activity and activity.name == act.name else False
            )
        )

    activity_select = ui.Select(
        placeholder="Activities",
        custom_id="activity_select",
        options=act_list
    )

    if callback:
        activity_select.callback = callback

    return activity_select

def get_character_info_sections(player: Player, server: Server, callback: Coroutine, **kwargs) -> list[ui.Section]:
    char_list = []

    emoji = kwargs.get("emoji", EDIT_EMOJI[0])
    character: Character = kwargs.get("character")
    select_emoji = kwargs.get("select_emoji")

    for char in player.active_characters[:24]:
        char_button = ui.Button(
            style=discord.ButtonStyle.blurple,
            emoji=emoji if not select_emoji else select_emoji if character and character.id == char.id else emoji,
            custom_id=f"{char.id}"
        )
        char_button.callback = callback

        char_list.append(
            ui.Section(
                ui.TextDisplay(
                    f"**{char.name}{'*' if char.primary_character == True else ''}**\n"
                    f"-# Level {char.level}\n"
                    f"-# {char.species_str} | {char.class_str}\n"
                    f"-# {char.currency:,} {server.currency_str} | {char.xp:,} xp"
                ),
                accessory=char_button
            )
        )

    return char_list

def get_character_request_sections(container: ui.Container, request: Request, callback: Coroutine = None):
    container.add_item(
        ui.TextDisplay(
            "## Requested for:"
        )
    )

    for player, characters in request.player_characters.items():
        for char in characters:
            char_text = ui.TextDisplay(
                f"{char.name} ({player.mention})"
            )

            char_button = ui.Button(
                emoji=DENIED_EMOJI[0],
                custom_id=f"remove_{char.id}"
            )

            if callback:
                char_button.callback = callback

            if request.player_id == player.id or not callback:
                container.add_item(char_text)

            else:
                container.add_item(
                    ui.Section(
                        char_text,
                        accessory=char_button
                    )
                )



