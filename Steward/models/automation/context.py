from typing import TYPE_CHECKING, Union, Optional
import discord

if TYPE_CHECKING:
    from Steward.bot import StewardContext
    from Steward.models.objects.character import Character
    from Steward.models.objects.player import Player
    from Steward.models.objects.servers import Server
    from Steward.models.objects.npc import NPC

class AutomationContext:

    def __init__(self,
                 ctx: Union["StewardContext", discord.Interaction] = None,
                 character: Optional["Character"] = None,
                 player: Optional["Player"] = None,
                 server: Optional["Server"] = None,
                 npc: Optional["NPC"] = None,
                 **kwargs
                 ):
            
        self.ctx = ctx
        self.character = character
        self.player = player
        self.server = server
        self.npc = npc
        
        # Any extras
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def to_dict(self) -> dict:
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith('_') and value is not None:
                result[key] = value
        return result
        