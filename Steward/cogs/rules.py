from datetime import datetime, timezone
import logging
import discord
from discord.ext import commands, tasks
from timeit import default_timer as timer


from Steward.bot import StewardBot
from Steward.models.automation.context import AutomationContext
from Steward.models.objects import request
from Steward.models.objects.form import Application
from Steward.models.objects.character import Character
from Steward.models.objects.enum import RuleTrigger
from Steward.models.objects.log import StewardLog
from Steward.models.objects.player import Player
from Steward.models.objects.request import Request
from Steward.models.objects.rules import StewardRule
from Steward.models.objects.servers import Server
from Steward.utils.discordUtils import is_staff
from Steward.utils.ruleUtils import execute_rules_for_trigger

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(RulesCog(bot))


class RulesCog(commands.Cog):
    bot: StewardBot
    
    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")
    
    @commands.Cog.listener()
    async def on_raw_member_remove(self, payload: discord.RawMemberRemoveEvent):
        guild = self.bot.get_guild(payload.guild_id)
        server = await Server.get_or_create(self.bot.db, guild)
        player= await Player.get_or_create(self.bot.db, server.get_member(payload.user.id))

        rules = await execute_rules_for_trigger(self.bot, server, RuleTrigger.member_leave.name, player=player)

        log.info(rules)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
       server = await Server.get_or_create(self.bot.db, member.guild)
       player = await Player.get_or_create(self.bot.db, member.guild)

       rules = await execute_rules_for_trigger(self.bot, server, RuleTrigger.member_join.name, player=player)

       log.info(rules)

    @commands.Cog.listener()
    async def on_new_character(self, ctx, character: Character, log_entry: StewardLog):
       guild = self.bot.get_guild(character.guild_id)
       server = await Server.get_or_create(self.bot.db, guild)
       player = await Player.get_or_create(self.bot.db, server.get_member(character.player_id))

       rules = await execute_rules_for_trigger(self.bot, server, RuleTrigger.new_character.name, player=player, character=character, log=log_entry, ctx=ctx)

       log.info(rules)
       
    @commands.Cog.listener()
    async def on_log(self, log_entry: StewardLog):
        log_entry = await StewardLog.fetch(self.bot, log_entry.id)

        rules = await execute_rules_for_trigger(self.bot, log_entry.server, RuleTrigger.log.name, character=log_entry.character, player=log_entry.player, log=log_entry)

        log.info(rules)

    @commands.Cog.listener()
    async def on_staff_point(self, staff: Player):
        server = await Server.get_or_create(self.bot.db, staff.guild)
        character = staff.primary_character

        rules = await execute_rules_for_trigger(self.bot, server, RuleTrigger.staff_point.name, character=character, player=staff)
        
        log.info(rules)

    @commands.Cog.listener()
    async def on_new_request(self, request: Request):
        guild = self.bot.get_guild(request.guild_id)
        server = await Server.get_or_create(self.bot.db, guild)
        rules = await execute_rules_for_trigger(self.bot, server, RuleTrigger.new_request.name, request=request, player=request.primary_player)

        log.info(rules)

    @commands.Cog.listener()
    async def on_new_application(self, application: Application):
        server = await Server.get_or_create(self.bot.db, application.player.guild)
        rules = await execute_rules_for_trigger(self.bot, server, RuleTrigger.new_application.name, application=application, player=application.player, character=application.character)

        log.info(rules)

    # Scheduled Rules Stuff
    @commands.Cog.listener()
    async def on_db_connected(self):
        log.info("Database connected, starting scheduler loop")
        self.check_scheduled_rules.start()

    def cog_unload(self):
        log.info("Stopping scheduler loop")
        self.check_scheduled_rules.cancel()
    
    @tasks.loop(minutes=1)
    async def check_scheduled_rules(self):
        try:
            current_time = datetime.now(timezone.utc)
            log.debug(f"Checking scheduled rules at {current_time}")
            
            # Get all scheduled rules
            scheduled_rules = await StewardRule.get_all_scheduled_rules(self.bot.db)
            
            if not scheduled_rules:
                log.debug("No scheduled rules found")
                return
            
            log.info(f"Found {len(scheduled_rules)} scheduled rules to check")
            
            for rule in scheduled_rules:
                try:
                    # Check if this rule should run now
                    if rule.should_run_now(current_time):
                        log.debug(f"Executing scheduled rule: {rule.name} (ID: {rule.id}) for guild {rule.guild_id}")
                        
                        # Get the server/guild
                        guild = self.bot.get_guild(rule.guild_id)
                        if not guild:
                            log.warning(f"Guild {rule.guild_id} not found for rule {rule.name}")
                            continue
                        
                        server = await Server.get_or_create(self.bot.db, guild)
                        
                        # Create automation context for scheduled rule
                        # For scheduled rules, we don't have a specific player/character context
                        context = AutomationContext(
                            server=server,
                            player=None,
                            character=None,
                            log=None,
                            ctx=None,
                            trigger="scheduled"
                        )
                        
                        # Evaluate condition if exists
                        if not rule.evaluate_condition(context):
                            log.debug(f"Rule {rule.name} condition not met, skipping")
                            continue
                        
                        # Execute the rule's actions
                        result = await rule.execute_action(self.bot, context)
                        
                        if result.get('success'):
                            log.info(f"Successfully executed scheduled rule: {rule.name}")
                            # Mark the rule as run
                            await rule.mark_as_run(current_time)
                        else:
                            log.error(f"Failed to execute scheduled rule {rule.name}: {result.get('error')}")
                            
                except Exception as e:
                    log.error(f"Error processing scheduled rule {rule.name}: {e}", exc_info=True)
                    
        except Exception as e:
            log.error(f"Error in check_scheduled_rules: {e}", exc_info=True)

    @check_scheduled_rules.before_loop
    async def before_check_scheduled_rules(self):
        """Wait for the bot to be ready before starting the loop"""
        await self.bot.wait_until_ready()
        log.info("Bot ready, scheduler will start")
    