import re

from discord import TYPE_CHECKING

from Steward.utils.discordUtils import get_selection

if TYPE_CHECKING:
    from Steward.models.objects.webhook import StewardWebhook
    from Steward.models.objects.character import Character


def find_character_by_name(name: str, characters: list["Character"]) -> list["Character"]:
    name_lower = name.lower()

    name_match = []
    nickname_match = []
    partial_match = []

    for c in characters:
        if c.name.lower() == name_lower:
            name_match.append(c)
        elif c.nickname and c.nickname.lower() == name_lower:
            nickname_match.append(c)
        elif name_lower in c.name.lower() or (c.nickname and name_lower in c.nickname.lower()):
            partial_match.append(c)

    return name_match or nickname_match or partial_match


async def handle_character_mentions(webhook: "StewardWebhook") -> None:
    # Regex to look for mentions {$<character name or nickname>}
    if not (char_mentions := re.findall(r"{\$([^}]*)}", webhook.content)):
        return
    
    characters = await webhook.ctx.guild.get_all_characters()
    mentioned_characters = set()

    for mention in char_mentions:
        matches = find_character_by_name(mention, characters)

        mention_char = None

        if len(matches) == 1:
            mention_char = matches[0]
        elif len(matches) > 1:
            # Cache member lookups
            member_map = {c: webhook.ctx.guild.get_member(c.player_id) for c in matches}
            choices = [
                f"{c.name} [{member.display_name}]"
                for c, member in member_map.items()
                if member
            ]

            if choice := await get_selection(
                webhook.ctx,
                choices,
                True,
                True,
                f"Type your choice in {webhook.ctx.channel.jump_url}",
                True,
                f"Found multiple matches for `{mention}`"
            ):
                mention_char = matches[choices.index(choice)]

        if mention_char:
            mentioned_characters.add(mention_char)
            webhook.content = webhook.content.replace(
                "{$" + mention + "}",
                f"[{mention_char.mention}](<discord:///users/{mention_char.player_id}>)"
            )

    # Send notifications after all mentions are processed
    for char in mentioned_characters:
        if member := webhook.ctx.guild.get_member(char.player_id):
            try:
                await member.send(
                    f"{webhook.player.mention} directly mentioned `{char.mention}` in:\n{webhook.ctx.channel.jump_url}"
                )
            except:
                pass