import asyncio
import re
import discord
import logging

from discord.ext import commands
from Steward.models.objects.character import Character
from Steward.models.objects.enum import WebhookType
from Steward.models.objects.exceptions import CharacterNotFound, StewardCommandError
from Steward.models.objects.player import Player
from Steward.models.objects.npc import NPC
from Steward.bot import StewardContext
from typing import Union

from Steward.utils.discordUtils import chunk_text, try_delete
from Steward.utils.webhookUtils import handle_character_mentions

log = logging.getLogger(__name__)

class StewardWebhook:
    player: Player
    ctx: StewardContext
    type: WebhookType
    
    content: str = None
    message: discord.Message = None

    npc: NPC = None
    character: Character = None
    # Adventure later
    adventure = None

    def __init__(self, ctx: StewardContext, **kwargs):
        self.ctx = ctx

        self.type = kwargs.get("type", WebhookType.character)

        if hasattr(self.ctx, "player") and self.ctx.player:
            self.player = self.ctx.player
        
        self.message = kwargs.get("message", ctx.message)
        self.adventure = kwargs.get("adventure")

    async def is_authorized(self) -> bool:
        if not self.npc:
            return False
        
        match self.type:
            case WebhookType.npc:
                roles_set = {r.id for r in self.player.roles}
                npc_set = set(self.npc.roles)

                return bool(
                    (roles_set & npc_set) or(
                        self.ctx.guild.is_admin(self.player)
                    )
                )
            
            case WebhookType.adventure:
                pass

        return False

    async def send(self) -> None:
        # Validation
        if not self.player and hasattr(self.ctx, "player") and self.ctx.player:
            self.player = self.ctx.player
        else:
            self.player = await Player.get_or_create(self.ctx.bot.db, self.ctx.author)

        match self.type:
            case WebhookType.say:
                self.content = self.message.content[5:]

                if self.content == "" or self.content.lower() == f"{self.ctx.bot.command_prefix}say":
                    return
                
                if not self.player.characters:
                    raise CharacterNotFound(self.player)
                
                # Find a character from the first part. Ex. >say "Billy"
                if match := re.match(r"^(['\"“”])(.*?)['\"“”]", self.content):
                    search = match.group(2)
                    self.character = next(
                        (
                            c
                            for c in self.player.characters
                            if search.lower() in c.name.lower()
                            or (c.nickname and search.lower() in c.nickname.lower())
                        ),
                        None,
                    )
                    if self.character:  
                        self.content = re.sub(
                            r"^(['\"“”])(.*?)['\"“”]\s*", "", self.content, count=1
                        )

                if not self.character:
                    self.character = await self.player.get_webhook_character(self.ctx.channel)

                # Add channel to current character if override specified
                if "{$channel}" in self.content:
                    updates = []

                    for char in self.player.characters:
                        if self.ctx.channel.id in char.channels:
                            char.channels.remove(self.ctx.channel.id)
                            updates.append(char.upsert())

                    self.character.channels.append(self.ctx.channel.id)
                    updates.append(char.upsert())

                    if updates:
                        await asyncio.gather(*updates)

                    self.content = re.sub(r"\{\$channel\}", "", self.content)

            case WebhookType.npc:
                if npc := self.ctx.guild.get_npc(key=self.ctx.invoked_with):
                    self.npc = npc
                    self.content = self.message.content[len(self.npc.key) + 2:]

            case WebhookType.adventure:
                pass

        # Final Checks
        if not self.npc and not self.character:
            return # Don't do an error here in case someone just mistakenly does something
        
        elif self.npc and not await self.is_authorized():
            raise StewardCommandError("You do not have authorization to do this.")
        

        if not self.npc or not self.character:
            return
        
        
        await handle_character_mentions(self)
        await try_delete(self.ctx.message)

        chunks = chunk_text(self.content, 2000)
            
        for chunk in chunks:
            try:
                if self.npc:
                    await self.npc.send_message(self.ctx, chunk)
                else:
                    await self.player.send_webhook_message(self.ctx, self.character, chunk)


                if self.ctx.channel.id not in self.ctx.guild.activity_excluded_channels:
                    await self.player.update_post_stats(self.npc if self.npc else self.character, self.ctx.message, content=chunk)

                    if len(chunk) > self.ctx.guild.activity_char_count_threshold:
                        # Update activity points
                        pass
            except:
                pass