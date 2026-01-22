import discord
from Steward.models.embeds import CharacterEmbed
from Steward.models.objects.character import Character
from Steward.models.objects.player import Player
from Steward.models.objects.servers import Server



class CharacterViewEmbed(CharacterEmbed):
    def __init__(
            self,
            author: "Player",
            server: "Server",
            player: "Player",
            character: "Character"
    ):
        super().__init__(
            author, 
            character, 
            title=f"Character Info - [{character.level}] {character.name}"
        )

        xp_level = server.get_level_for_xp(character.xp)

        self.description = (
            f"**Player**: {player.mention}\n"
            f"**Species**: {character.species_str}\n"
            f"**Class**: {character.class_str}\n\n"
            f"**{server.currency_str}**: {character.currency}\n"
            f"**XP**: {character.xp} (Level {xp_level}{' eligible' if xp_level > character.level else ''})"
        )

        if server.activity_points:
            activity_point = server.get_activity_for_points(character.activity_points)
            self.description += (
                "\n"
                f"**Activity Points**: {character.activity_points} ({'0' if not activity_point else activity_point.level})"
            )