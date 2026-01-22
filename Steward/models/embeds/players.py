from typing import TYPE_CHECKING
import discord

from Steward.bot import StewardContext
from Steward.models.embeds import PlayerEmbed
from constants import ZWSP3

if TYPE_CHECKING:
    from Steward.models.objects.player import Player
    from Steward.models.objects.character import Character

class PlayerOverviewEmbed(PlayerEmbed):
    def __init__(
            self,
            author: "Player",
            player: "Player"
            ):
        super().__init__(author, title=f"Information for {player.display_name}")
        self.set_thumbnail(
            url=(
                player.display_avatar.url if player.display_avatar else None
            )
        )

        self.color = player.color

        self.description = "I have no idea what to put here yet....who is this yahoo?"

        if player.active_characters:
            char_str = ""

            for character in player.active_characters:
                char_str += (
                    f"[{character.level}] {character.name}\n"
                    f"{ZWSP3} {character.species_str} // {character.class_str}\n\n"
                )

            self.add_field(name=f"Character Information", value=char_str, inline=False)