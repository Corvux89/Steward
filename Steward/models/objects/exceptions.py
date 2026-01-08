import discord
from discord.ext import commands

class StewardCommandError(commands.CommandError):
    def __init__(self, message):
        return super().__init__(f"{message}")
    
class StewardError(discord.ApplicationCommandError):
    def __init__(self, message):
        super().__init__(f"{message}")

class CharacterNotFound(StewardError):
    def __init__(self, member):
        super().__init__(f"No character information found for {member.mention}")