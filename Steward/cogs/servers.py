import io
import discord
import logging
import csv
import json
from discord.ext import commands
from timeit import default_timer as timer

from Steward.bot import StewardBot, StewardContext
from Steward.models.objects.activityPoints import ActivityPoints
from Steward.models.objects.enum import RuleTrigger
from Steward.models.objects.exceptions import StewardError
from Steward.models.objects.levels import Levels
from Steward.models.objects.npc import NPC
from Steward.models.objects.servers import Server
from Steward.models.objects.activity import Activity
from Steward.utils.discordUtils import is_admin

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(ServerCog(bot))


class ServerCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    server_commands = discord.SlashCommandGroup(
        "server",
        "Server administration/configuration commands",
        contexts=[discord.InteractionContextType.guild]
    )

    config_options = [
        discord.OptionChoice(
            "Server Settings",
            value="server"
        ),
        discord.OptionChoice(
            "NPCS",
            value="npc"
        ),
        discord.OptionChoice(
            "Activity Points",
            value="ap"
        ),
        discord.OptionChoice(
            "Levels and Tiers",
            value="levels"
        ),
        discord.OptionChoice(
            "Activities",
            value="activity"
        ),
        discord.OptionChoice(
            "Rules",
            value="rules"
        ),
        discord.OptionChoice(
            "Applications",
            value="applications"
        ),
        discord.OptionChoice(
            "All",
            value="all"
        )
    ]

    @server_commands.command(
        name="export_config",
        description="Export a server configuration item to .csv"
    )
    @commands.check(is_admin)
    async def export_config(
        self,
        ctx: "StewardContext",
        config_item: discord.Option(
            discord.SlashCommandOptionType(3),
            description="Configuration item",
            required=True,
            choices=config_options
        )
    ):
        await ctx.defer()
        files = []

        if config_item == "server" or config_item == "all":
            files.append(
                discord.File(
                    await self._server_config(ctx.server),
                    description="Server Information",
                    filename="Server.csv"
                )
            )

        if config_item == "npc" or config_item == "all":
            files.append(
                discord.File(
                    await self._npc_config(ctx.server),
                    description="NPC Information",
                    filename="NPC.csv"
                )
            )

        if config_item == "ap" or config_item == "all":
            files.append(
                discord.File(
                    await self._activity_point_config(ctx.server),
                    description="Activity Points Information",
                    filename="Activity Points.csv"
                )
            )

        if config_item == "levels" or config_item == "all":
            files.append(
                discord.File(
                    await self._level_config(ctx.server),
                    description="Level Information",
                    filename="Activity Points.csv"
                )
            )

        if config_item == "activity" or config_item == "all":
            files.append(
                discord.File(
                    await self._activities_config(ctx.server),
                    "Activities.csv",
                    description="Activity Information"
                )
            )

        if config_item == "rules" or config_item == "all":
            files.append(
                discord.File(
                    await self._rules_config(ctx.server),
                    description="Rules Configuration",
                    filename="Rules.csv"
                )
            )

        if config_item == "applications" or config_item == "all":
            files.append(
                discord.File(
                    await self._application_config(ctx.server),
                    description="Applications Configuration",
                    filename="Applications.csv"
                )
            )
        

        await ctx.respond(files=files)

    @server_commands.command(
        name="import_config",
        description="Import a configuraiton file"
    )
    @commands.check(is_admin)
    async def import_config(self,
                            ctx: "StewardContext",
                            file: discord.Option(
                                discord.SlashCommandOptionType.attachment,
                                description="CSV file to import",
                                required=True
                            )):
        await ctx.defer()

        if not file.filename.lower().endswith('.csv'):
            raise StewardError("File must be a .csv file.")
        
        f_name_lower = file.filename.lower()

        try:
            content = await file.read()
            text = content.decode('utf-8')
        except Exception as e:
            raise StewardError(e)

        try:
            if f_name_lower.startswith('server'):
                await self._server_config(ctx.server, text)

            elif f_name_lower.startswith("npc"):
                await self._npc_config(ctx.server, text)

            elif f_name_lower.startswith('activity points') or f_name_lower.startswith('activity_points'):
                await self._activity_point_config(ctx.server, text)

            elif f_name_lower.startswith('level'):
                await self._level_config(ctx.server, text)

            elif f_name_lower.startswith('activities'):
                await self._activities_config(ctx.server, text)

            elif f_name_lower.startswith('rules'):
                await self._rules_config(ctx.server, text)

            elif f_name_lower.startswith('applications'):
                await self._application_config(ctx.server, text)

            else:
                return await ctx.respond("I don't know aht you're trying to do")
            await ctx.respond(f"Successfully imported configuration!")
        
        except Exception as e:
            raise StewardError(e)

    async def _server_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "max_level": "Max Level",
            "currency_limit_expr": "Currency Limit Expression",
            "xp_limit_expr": "XP Limit Expression",
            "xp_global_limit_expr": "Global XP Limit",
            "max_characters_expr": "Max Characters Expression",
            "activity_char_count_threshold": "Activity Character Count Threshold",
            "activity_excluded_channels": "Activity Excluded Channels",
            "currency_label": "Currency Label",
            "staff_role_id": "Staff Role ID",
            "staff_request_channel_id": "Staff Request Channel ID"
        }
        
        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            row = next(reader)

            for attr, header in header_mapping.items():
                if header in row:
                    value = row[header]
                
                    if value == '' or value is None:
                        value = None
                    elif attr == 'max_level' or attr == 'activity_char_count_threshold':
                        value = int(value)
                    elif attr == 'staff_role_id' or attr == 'staff_request_channel_id':
                        value = int(value) if value else None
                    elif attr == 'activity_excluded_channels':
                        value = [int(x.strip()) for x in value.strip('[]').split(',') if x.strip()]

                    setattr(server, attr, value)
            await server.save()
        else:
            schema = Server.ServerSchema()
            data = schema.dump(server)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()
            
            # Map the data keys to human-readable headers
            row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
            writer.writerow(row)
            
            output.seek(0)
            return output
    
    async def _npc_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "key": "Key",
            "name": "Name",
            "avatar_url": "Avatar URL",
            "roles": "Additional Allowed Roles"
        }

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                data['guild_id'] = server.id

                if 'roles' in data and data['roles']:
                    data['roles'] = [int(x.strip()) for x in data['roles'].strip('[]').split(',') if x.strip()]
                else:
                    data['roles'] = []

                npc = NPC(self.bot.db, **data)
                await npc.upsert()
                await npc.register_command(self.bot)
            await server.load_npcs()

        else:
            schema = NPC.NPCSchema(self.bot.db)        
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            for npc in server.npcs:
                data = schema.dump(npc)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output
    
    #TODO: Verify
    async def _activity_point_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "level": "Level",
            "points": "# of Points Required",
            "xp_expr": "XP Reward Expression",
            "currency_expr": "Currency Reward Expression"
        }

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                data = {header_mapping[k]: v for k, v in row.items() if k in header_mapping}
                data['guild_id'] = server.id

                data['level'] = int(data['level'])
                data['points'] = int(data['points'])

                if not data.get('xp_expr'):
                    data['xp_expr'] = None
                
                if not data.get('currency_expr'):
                    data['currency_expr'] = None

                ap = ActivityPoints(self.bot.db, **data)
                await ap.upsert()
            await server.load_acitvity_points()
        else:
            schema = ActivityPoints.ActivityPointsSchema(self.bot.db)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            for ap in server.activity_points:
                data = schema.dump(ap)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output
    
    #TODO: VERify
    async def _level_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "level": "Level",
            "xp": "Minimum XP",
            "tier": "Level Tier"
        }
        
        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                data = {k: row[v] for k, v in header_mapping.items() if v in row}
                data["guild_id"] = server.id

                data["level"] = int(data["level"])
                data["xp"] = int(data["xp"])
                data["tier"] = int(data["tier"])

                level = Levels(self.bot.db, **data)
                await level.upsert()

            await server.load_levels()
        else:
            schema = Levels.LevelSchema(self.bot.db)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            for l in server.levels:
                data = schema.dump(l)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output
    
    # TODO: Verify
    async def _activities_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "name": "Name",
            "currency_expr": "Currency Reward Expression",
            "xp_expr": "XP Reward Expression",
            "limited": "Limited/Capped?",
            "active": "Active"
        }

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                data = {k: row[v] for k, v in header_mapping.items() if v in row}
                data['guild_id'] = server.id

                if 'limited' in data:
                    data['limited'] = data["limited"].lower() in ('true', '1', 'yes')
                if 'active' in data:
                    data['active'] = data["active"].lower() in ('true', '1', 'yes')

                if not data.get('currency_expr'):
                    data['currency_expr'] = None
                if not data.get('xp_expr'):
                    data['xp_expr'] = None

                if activity := server.get_activity(data['name']):
                    for k, v in data.items():
                        if k != 'guild_id':
                            setattr(activity, k, v)
                else:
                    activity = Activity(self.bot.db, **data)

                await activity.upsert()

            await server.load_activities()

        else:
            schema = Activity.ActivitySchema(self.bot.db)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            for act in server.activities:
                data = schema.dump(act)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output

    async def _rules_config(self, server: Server, csv_text: str = None):
        from Steward.models.objects.rules import StewardRule

        header_mapping = {
            "id": "id",
            "name": "Name",
            "trigger": "Trigger",
            "schedule_cron": "Schedule Cron",
            "enabled": "Enabled",
            "condition_expr": "Condition Expression",
            "priority": "Priority",
            "action_data": "Action Data (JSON)"
        }

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                data['guild_id'] = server.id

                
                if 'id' in data and data['id'] == '':
                    del data['id']

                if 'enabled' in data and data['enabled']:
                    data['enabled'] = data["enabled"].lower() in ('true', '1', 'yes')
                else:
                    data['enabled'] = True

                if 'priority' in data and data['priority']:
                    data['priority'] = int(data['priority'])
                else:
                    data['priority'] = 0

                if 'action_data' in data and data['action_data']:
                    try:
                        data['action_data'] = json.loads(data['action_data'])
                    except json.JSONDecodeError:
                        raise StewardError(f"Invalid JSON in action_data for rule '{data.get('name')}': {data['action_data']}")
                else:
                    data['action_data'] = {}

                if 'trigger' in data and data['trigger']:
                    data['trigger'] = RuleTrigger.from_string(data['trigger'])
                
            
                existing_rule = await StewardRule.fetch(self.bot.db, server.id,  id=data['id'] if 'id' in data else None, name=data['name'])
                if existing_rule:
                    existing_rule.update(data)
                    rule = existing_rule
                else:
                    rule = StewardRule(self.bot.db, **data)
                await rule.upsert()

        else:
            schema = StewardRule.RuleSchema(self.bot.db)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            rules = await StewardRule.get_all_rules_for_server(
                self.bot.db, 
                server.id
            )
            
            for rule in rules:
                data = schema.dump(rule)
                row = {}
                for k, v in header_mapping.items():
                    if k == 'action_data':
                        row[v] = json.dumps(data.get(k, {}))
                    elif k == 'trigger':
                        row[v] = k.name
                    else:
                        row[v] = data.get(k)
                writer.writerow(row)

            output.seek(0)
            return output
        
    async def _application_config(self, server: Server, csv_text: str = None):
        from Steward.models.objects.application import ApplicationTemplate

        header_mapping = {
            "name": "Name",
            "template": "Template",
            "character_specific": "Character Specific?"
        }

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))

            for row in reader:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                data['guild_id'] = server.id

                if 'character_specific' in data:
                    data['character_specific'] = data["character_specific"].lower() in ('true', '1', 'yes')

                application = ApplicationTemplate(self.bot.db, **data)
                await application.upsert()

        else:
            schema = Activity.ActivitySchema(self.bot.db)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            applications = await ApplicationTemplate.fetch_all(self.bot.db, server.id)

            for application in applications:
                data = schema.dump(application)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output