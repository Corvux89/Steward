from typing import TYPE_CHECKING, Union, Optional
import discord

if TYPE_CHECKING:
    from Steward.bot import StewardApplicationContext
    from Steward.models.objects.character import Character
    from Steward.models.objects.player import Player
    from Steward.models.objects.servers import Server
    from Steward.models.objects.npc import NPC
    from Steward.models.objects.log import StewardLog
    from Steward.models.objects.rules import StewardRule
    from Steward.models.objects.form import Application
    from Steward.models.objects.request import Request
    from Steward.models.objects.patrol import Patrol

class AutomationContext:
    character: "Character" = None
    player: "Player" = None
    log: "StewardLog" = None
    rule: "StewardRule" = None
    ctx = None
    server: "Server" = None
    npc: "NPC" = None
    request: "Request" = None
    application: "Application" = None
    patrol: "Patrol" = None

    def __init__(self,
                 ctx: Union["StewardApplicationContext", discord.Interaction] = None,
                 character: Optional["Character"] = None,
                 player: Optional["Player"] = None,
                 server: Optional["Server"] = None,
                 npc: Optional["NPC"] = None,
                 log: Optional["StewardLog"] = None,
                 request: Optional["Request"] = None,
                 application: Optional["Application"] = None,
                 patrol: Optional["Patrol"] = None,
                 **kwargs
                 ):
            
        self.ctx = ctx
        self.character = character
        self.player = player
        self.server = server
        self.npc = npc
        self.log=log
        self.request = request
        self.application = application
        self.patrol = patrol
        
        # Any extras
        for key, value in kwargs.items():
            setattr(self, key, value)