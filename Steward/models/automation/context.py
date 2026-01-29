from typing import TYPE_CHECKING, Union, Optional
import discord

if TYPE_CHECKING:
    from Steward.bot import StewardContext
    from Steward.models.objects.character import Character
    from Steward.models.objects.player import Player
    from Steward.models.objects.servers import Server
    from Steward.models.objects.npc import NPC
    from Steward.models.objects.log import StewardLog
    from Steward.models.objects.rules import StewardRule
    from Steward.models.objects.request import Request

class AutomationContext:
    character: "Character" = None
    player: "Player" = None
    log: "StewardLog" = None
    rule: "StewardRule" = None
    ctx = None
    server: "Server" = None
    npc: "NPC" = None
    request: "Request" = None

    def __init__(self,
                 ctx: Union["StewardContext", discord.Interaction] = None,
                 character: Optional["Character"] = None,
                 player: Optional["Player"] = None,
                 server: Optional["Server"] = None,
                 npc: Optional["NPC"] = None,
                 log: Optional["StewardLog"] = None,
                 request: Optional["Request"] = None,
                 **kwargs
                 ):
            
        self.ctx = ctx
        self.character = character
        self.player = player
        self.server = server
        self.npc = npc
        self.log=log
        self.request = request
        
        # Any extras
        for key, value in kwargs.items():
            setattr(self, key, value)