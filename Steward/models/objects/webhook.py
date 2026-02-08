import asyncio
import re
import discord
import logging

from discord.ext import commands
from Steward.models.objects.character import Character
from Steward.models.objects.enum import WebhookType
from Steward.models.objects.exceptions import StewardCommandError
from Steward.models.objects.player import Player
from Steward.models.objects.npc import NPC
from Steward.bot import StewardContext

from Steward.utils.discordUtils import chunk_text, try_delete
from Steward.utils.webhookUtils import get_character_name, get_player_name, handle_character_mentions

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

    async def send(self) -> None:
        # Validation
        if not self.player and hasattr(self.ctx, "player") and self.ctx.player:
            self.player = self.ctx.player
        else:
            self.player = await Player.get_or_create(self.ctx.bot.db, self.ctx.author)

        match self.type:
            case WebhookType.character:
                self.content = self.message.content[len(self.ctx.invoked_with)+2:]

                if self.content == "" or self.content.lower() == f"{self.ctx.bot.command_prefix}say":
                    return
                
                if not self.player.active_characters:
                    raise StewardCommandError(f"No character information found for {self.ctx.player.mention}")
                
                # Find a character from the first part. Ex. >say "Billy"
                if match := re.match(r"^(['\"“”])(.*?)['\"“”]", self.content):
                    search = match.group(2)
                    self.character = next(
                        (
                            c
                            for c in self.player.active_characters
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

                    for char in self.player.active_characters:
                        if self.ctx.channel.id in char.channels:
                            char.channels.remove(self.ctx.channel.id)
                            updates.append(char.upsert())

                    self.character.channels.append(self.ctx.channel.id)
                    updates.append(char.upsert())

                    if updates:
                        await asyncio.gather(*updates)

                    self.content = re.sub(r"\{\$channel\}", "", self.content)

            case WebhookType.npc:
                if npc := await self.ctx.server.get_npc(key=self.ctx.invoked_with):
                    self.npc = npc
                    self.content = self.message.content[len(self.npc.key) + 2:]

            case WebhookType.adventure:
                pass

        # Final Checks
        if not self.npc and not self.character:
            return # Don't do an error here in case someone just mistakenly does something
        
        elif self.npc and not await self.user_is_authorized_for_npc():
            raise StewardCommandError("You do not have authorization to do this.")
        
        
        await handle_character_mentions(self)
        await try_delete(self.ctx.message)

        chunks = chunk_text(self.content, 2000)
            
        for chunk in chunks:
            try:
                if self.npc:
                    await self.npc.send_message(self.ctx, chunk)
                else:
                    await self.player.send_webhook_message(self.ctx, self.character, chunk)


                if self.ctx.channel.id not in self.ctx.server.activity_excluded_channels:
                    await self.player.update_post_stats(self.npc if self.npc else self.character, self.ctx.message, content=chunk)

                    if len(chunk) >= self.ctx.server.activity_char_count_threshold:
                        reward_char = self.character or self.player.primary_character
                        await reward_char.update_activity_points(self.ctx)


            except Exception as e:
                log.error(e)
                pass

    async def edit(self, content: str) -> None:
        self.content = content

        match self.type:
            case WebhookType.character | WebhookType.npc:
                if hasattr(self.ctx, "player") and self.ctx.player and not self.player:
                    self.player = self.ctx.player
                else:
                    self.player = await Player.get_or_create(self.ctx.bot.db, self.ctx.author)

                await handle_character_mentions(self)

                try:
                    # Edit the message
                    if WebhookType.character:
                        await self.player.edit_webhook_message(self.ctx, self.message.id, self.content)
                    else:
                        await self.npc.edit_message(self.ctx, self.message.id, self.content)

                    if self.ctx.channel.id not in self.ctx.server.activity_excluded_channels:
                        # Revert the original message stats using the old content
                        await self.player.update_post_stats(self.character or self.npc, self.message, retract=True)

                        # Apply the new message stats using the new content
                        await self.player.update_post_stats(self.character or self.npc, self.message, content=self.content)

                        # Activity Points
                        reward_char = self.character or self.player.primary_character

                        # - Check if we have to take away points (lost length)
                        if (
                            len(self.content) < self.ctx.server.activity_char_count_threshold
                            and len(self.message.content) >= self.ctx.server.activity_char_count_threshold
                        ):
                            await reward_char.update_activity_points(self.ctx, False)
                        
                        # - Do we need to give a reward now?
                        elif (
                            len(self.content) >= self.ctx.server.activity_char_count_threshold
                            and len(self.message.content) < self.ctx.server.activity_char_count_threshold
                         ):
                            await reward_char.update_activity_points(self.ctx)
                        
                except Exception as e: 
                    await self.player.send(
                        f"Error editing message in {self.ctx.channel.jump_url}. Try again."
                    )

                    await self.player.send(f"```{self.content}```")

    async def delete(self) -> None:
        if self.ctx.channel.id not in self.ctx.server.activity_excluded_channels:
            await self.player.update_post_stats(
                self.character or self.npc,
                self.message,
                retract=True
            )

            if len(self.message.content) >= self.ctx.server.activity_char_count_threshold:
                reward_char = self.character or self.player.primary_character
                await reward_char.update_activity_points(self.ctx, False)
        
        await self.message.delete()

    async def is_valid_message(self, **kwargs) -> bool:
        if not self.message.author.bot:
            return False
        
        match self.type:
            case WebhookType.character:
                if kwargs.get("update_player", False):
                    if (name := get_player_name(self)) and (member := self.message.guild.get_member_named(name)):
                        self.player = await Player.get_or_create(self.ctx.bot.db, member)
                    else:
                        return False
                    
                if char_name := get_character_name(self):
                    for char in self.player.active_characters:
                        if char.name.lower() == char_name.lower():
                            self.character = char
                            return True
        
            case WebhookType.npc:
                if npc := await self.ctx.server.get_npc(name=self.message.author.name):
                    self.npc = npc
                    return True
                        
        return False
    
    async def user_is_authorized_for_npc(self) -> bool:
        if not self.npc:
            return False
        
        match self.type:
            case WebhookType.npc:
                user_roles = [role.id for role in self.player.roles]

                return bool(
                    (
                        set(user_roles) &
                        set(self.npc.roles)
                        ) or
                    self.ctx.server.is_admin(self.player)
                )
            
        return False