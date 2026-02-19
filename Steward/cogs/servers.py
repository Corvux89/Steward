import io
import discord
import logging
import csv
import json
import uuid
from discord.ext import commands
from timeit import default_timer as timer

from Steward.bot import StewardBot, StewardApplicationContext
from Steward.models.objects.activityPoints import ActivityPoints
from Steward.models.objects.auctionHouse import AuctionHouse, Item, Shelf
from Steward.models.objects.dashboards import CategoryDashboard
from Steward.models.objects.enum import RuleTrigger
from Steward.models.objects.exceptions import StewardError
from Steward.models.objects.levels import Levels
from Steward.models.objects.npc import NPC
from Steward.models.objects.servers import Server
from Steward.models.objects.activity import Activity
from Steward.models.views.auctionHouse import AuctionHouseView
from Steward.utils.autocompleteUtils import auction_house_autocomplete
from Steward.utils.discordUtils import is_admin

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(ServerCog(bot))

# TODO: Cleanup record removal/inactivation

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
            "Forms",
            value="forms"
        ),
        discord.OptionChoice(
            "Dashboards",
            value="dashboards"
        ),
        discord.OptionChoice(
            "Auction Houses",
            value="auction_houses"
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
        ctx: "StewardApplicationContext",
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
                    filename="Levels.csv"
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

        if config_item == "forms" or config_item == "all":
            files.append(
                discord.File(
                    await self._form_config(ctx.server),
                    description="Form Configuration",
                    filename="forms.csv"
                )
            )

        if config_item == "dashboards" or config_item == "all":
            files.append(
                discord.File(
                    await self._dashboard_config(ctx.server),
                    description="Dashboards",
                    filename="dashboards.csv"
                )
            )

        if config_item == "auction_houses" or config_item == "all":
            files.append(
                discord.File(
                    await self._auction_house_config(ctx.server),
                    description="Auction Houses",
                    filename="auction_houses.csv"
                )
            )
        

        await ctx.respond(files=files)

    @server_commands.command(
        name="import_config",
        description="Import a configuraiton file"
    )
    @commands.check(is_admin)
    async def import_config(self,
                            ctx: "StewardApplicationContext",
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

            elif f_name_lower.startswith('forms'):
                await self._form_config(ctx.server, text)

            elif f_name_lower.startswith("dashboards"):
                await self._dashboard_config(ctx.server, text)

            elif f_name_lower.startswith("auction_houses") or f_name_lower.startswith("auction houses"):
                await self._auction_house_config(ctx.server, text)

            else:
                return await ctx.respond("I don't know aht you're trying to do")
            await ctx.respond(f"Successfully imported configuration!")
        
        except Exception as e:
            raise StewardError(e)

    @server_commands.command(
        name="export_auction_inventory",
        description="Export item inventory definitions for one auction house"
    )
    @commands.check(is_admin)
    async def export_auction_inventory(
        self,
        ctx: "StewardApplicationContext",
        auction_house: discord.Option(
            str,
            description="Auction house name or ID",
            required=True,
            autocomplete=auction_house_autocomplete
        )
    ):
        await ctx.defer()

        house = await self._resolve_auction_house_for_server(ctx.server, auction_house)

        await ctx.respond(
            file=discord.File(
                await self._auction_inventory_config(house),
                description=f"Auction Inventory - {house.name}",
                filename=f"auction_inventory_{house.name}.csv"
            )
        )

    @server_commands.command(
        name="import_auction_inventory",
        description="Import item inventory definitions for one auction house"
    )
    @commands.check(is_admin)
    async def import_auction_inventory(
        self,
        ctx: "StewardApplicationContext",
        auction_house: discord.Option(
            str,
            description="Auction house name or ID",
            required=True,
            autocomplete=auction_house_autocomplete
        ),
        file: discord.Option(
            discord.SlashCommandOptionType.attachment,
            description="CSV file to import",
            required=True
        )
    ):
        await ctx.defer()

        if not file.filename.lower().endswith('.csv'):
            raise StewardError("File must be a .csv file.")

        house = await self._resolve_auction_house_for_server(ctx.server, auction_house)

        try:
            content = await file.read()
            text = content.decode('utf-8')
            await self._auction_inventory_config(house, text)
        except Exception as e:
            raise StewardError(e)

        await ctx.respond(f"Successfully imported inventory for {house.name}.")

    @server_commands.command(
        name="export_auction_shelves",
        description="Export shelf definitions for one auction house"
    )
    @commands.check(is_admin)
    async def export_auction_shelves(
        self,
        ctx: "StewardApplicationContext",
        auction_house: discord.Option(
            str,
            description="Auction house name or ID",
            required=True,
            autocomplete=auction_house_autocomplete
        )
    ):
        await ctx.defer()

        house = await self._resolve_auction_house_for_server(ctx.server, auction_house)

        await ctx.respond(
            file=discord.File(
                await self._auction_shelves_config(house),
                description=f"Auction Shelves - {house.name}",
                filename=f"auction_shelves_{house.name}.csv"
            )
        )

    @server_commands.command(
        name="import_auction_shelves",
        description="Import shelf definitions for one auction house"
    )
    @commands.check(is_admin)
    async def import_auction_shelves(
        self,
        ctx: "StewardApplicationContext",
        auction_house: discord.Option(
            str,
            description="Auction house name or ID",
            required=True,
            autocomplete=auction_house_autocomplete
        ),
        file: discord.Option(
            discord.SlashCommandOptionType.attachment,
            description="CSV file to import",
            required=True
        )
    ):
        await ctx.defer()

        if not file.filename.lower().endswith('.csv'):
            raise StewardError("File must be a .csv file.")

        house = await self._resolve_auction_house_for_server(ctx.server, auction_house)

        try:
            content = await file.read()
            text = content.decode('utf-8')
            await self._auction_shelves_config(house, text)
        except Exception as e:
            raise StewardError(e)

        await ctx.respond(f"Successfully imported shelves for {house.name}.")

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
            "staff_role_id": "Staff Role ID"
        }
        
        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            row = next(reader)

            for attr, header in header_mapping.items():
                if header in row:
                    value = row[header]
                
                    if value == '' or value is None:
                        value = None
                    elif attr == 'max_level' or attr == 'activity_char_count_threshold' or attr == 'staff_role_id':
                        value = int(value)
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
            await server.load_npcs()
            csv_keys = set()
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
                csv_keys.add(npc.key)

            for npc in server.npcs:
                if npc.key not in csv_keys:
                    await npc.delete()
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
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                data['guild_id'] = server.id

                data['level'] = int(data['level'])
                data['points'] = int(data['points'])

                if not data.get('xp_expr'):
                    data['xp_expr'] = None
                
                if not data.get('currency_expr'):
                    data['currency_expr'] = None

                ap = ActivityPoints(self.bot.db, **data)
                await ap.upsert()
            await server.load_activity_points()
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
    
    async def _level_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "level": "Level",
            "xp": "Minimum XP",
            "tier": "Level Tier"
        }
        
        if csv_text:
            await server.load_levels()
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)

            if not rows:
                raise StewardError("Levels import must include at least one row.")

            csv_levels = set()
            for row in rows:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                data["guild_id"] = server.id

                data["level"] = int(data["level"])
                data["xp"] = int(data["xp"])
                data["tier"] = int(data["tier"])

                level = Levels(self.bot.db, **data)
                await level.upsert()
                csv_levels.add(level.level)

            for existing_level in server.levels:
                if existing_level.level not in csv_levels:
                    await existing_level.delete()

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
    
    async def _activities_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "name": "Name",
            "verb": "Verb",
            "admin_only": "Admin Only",
            "currency_expr": "Currency Reward Expression",
            "xp_expr": "XP Reward Expression",
            "limited": "Limited/Capped?",
            "allow_override": "Allow value overrides?",
            "inverse_override": "Inverse override?",
            "active": "Active"
        }

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                data['guild_id'] = server.id

                if 'limited' in data:
                    data['limited'] = data["limited"].lower() in ('true', '1', 'yes')
                if 'active' in data:
                    data['active'] = data["active"].lower() in ('true', '1', 'yes')
                if 'allow_override' in data:
                    data['allow_override'] = data["allow_override"].lower() in ('true', '1', 'yes')
                if 'inverse_override' in data:
                    data['inverse_override'] = data["inverse_override"].lower() in ('true', '1', 'yes')
                if 'admin_only' in data:
                    data['admin_only'] = data["admin_only"].lower() in ('true', '1', 'yes')

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
                        row[v] = rule.trigger.name
                    else:
                        row[v] = data.get(k)
                writer.writerow(row)

            output.seek(0)
            return output
        
    async def _form_config(self, server: Server, csv_text: str = None):
        from Steward.models.objects.form import FormTemplate

        header_mapping = {
            "name": "Name",
            "content": "Content",  # Changed from "fields" to "content" to match FormTemplate
            "character_specific": "Character Specific?"
        }

        if csv_text:
            existing_templates = await FormTemplate.fetch_all(self.bot.db, server.id)
            csv_names = set()
            reader = csv.DictReader(io.StringIO(csv_text))

            for row in reader:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                data['guild_id'] = server.id

                if 'content' in data and data['content']:
                    try:
                        data['content'] = json.loads(data['content'])
                    except json.JSONDecodeError:
                        raise StewardError(f"Invalid JSON in content for application template '{data.get('name')}': {data['content']}")

                if 'character_specific' in data:
                    data['character_specific'] = data["character_specific"].lower() in ('true', '1', 'yes')

                application = FormTemplate(self.bot.db, **data)
                await application.upsert()
                csv_names.add(application.name)

            for template in existing_templates:
                if template.name not in csv_names:
                    await template.delete()

        else:
            schema = FormTemplate.ApplicationTemplateSchema(self.bot.db)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            applications = await FormTemplate.fetch_all(self.bot.db, server.id)

            for application in applications:
                data = schema.dump(application)
                row = {}
                
                for k, v in header_mapping.items():
                    if k == 'content':
                        row[v] = json.dumps(data.get(k, []))
                    else:
                        row[v] = data.get(k)
                writer.writerow(row)

            output.seek(0)
            return output
        
    async def _dashboard_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "id": "Dashboard ID",
            "channel_id": "Display Channel",
            "category_id": "Dashboard Channel Category",
            "excluded_channel_ids": "Excluded Channels"
        }
        dashboards = await CategoryDashboard.fetch_all(self.bot, server.id)

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            dashboard_ids = set()

            for row in reader:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                data["guild_id"] = server.id

                if 'id' in data and data['id'] == '':
                    del data['id']

                if 'excluded_channel_ids' in data and data['excluded_channel_ids']:
                    data['excluded_channel_ids'] = [int(x.strip()) for x in data['excluded_channel_ids'].strip('[]').split(',') if x.strip()]
                else:
                    data['excluded_channel_ids'] = []

                data['channel_id'] = int(data['channel_id'])
                data['category_id'] = int(data['category_id'])

                dashboard = None
                id_val = data.get('id') if 'id' in data else None
                if id_val:
                    dashboard = next((d for d in dashboards if str(getattr(d, 'id', None)) == str(id_val)), None)
                if not dashboard:
                    dashboard = next((d for d in dashboards if getattr(d, 'channel_id', None) == data['channel_id'] and getattr(d, 'category_id', None) == data['category_id']), None)

                if dashboard:
                    for k, v in data.items():
                        if k != 'id':
                            setattr(dashboard, k, v)
                    await dashboard.upsert()
                    await dashboard.refresh()
                    dashboard_ids.add(getattr(dashboard, 'id', None))
                else:
                    dashboard = CategoryDashboard(self.bot, **data)
                    message = await dashboard.channel.send("loading")
                    await message.pin()
                    dashboard.message_id = message.id
                    dashboard._message = message
                    await dashboard.upsert()
                    await dashboard.refresh()
                    dashboard_ids.add(getattr(dashboard, 'id', None))

            for dashboard in dashboards:
                if dashboard.id not in dashboard_ids:
                    await dashboard.delete()

        else:
            schema = CategoryDashboard.CategoryDashboardSchema()
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            for dashboard in dashboards:
                data = schema.dump(dashboard)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output

    async def _auction_house_config(self, server: Server, csv_text: str = None):
        header_mapping = {
            "id": "House ID",
            "name": "Name",
            "channel_id": "Channel ID",
            "min_bid_percent": "Minimum Bid %",
            "auction_length": "Auction Length (Hours)",
            "reroll_interval": "Reroll Interval (Hours)"
        }

        houses = [h for h in (await AuctionHouse.fetch_all(self.bot, load_related=True)) if h.guild_id == server.id]

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
            retained_house_ids = set()
            by_id = {str(house.id): house for house in houses if house.id}
            by_name = {house.name.lower(): house for house in houses if house.name}

            for row in rows:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                incoming_id = self._parse_optional_uuid(data.get("id"))
                incoming_name = self._normalize_csv_value(data.get("name"))

                if not incoming_name:
                    raise StewardError("Auction house Name is required.")

                incoming_channel_id = self._parse_required_int(data.get("channel_id"), "Channel ID")

                house = None
                if incoming_id:
                    house = by_id.get(str(incoming_id))
                if not house:
                    house = by_name.get(incoming_name.lower())

                is_new_house = house is None

                if not house:
                    house = AuctionHouse(
                        self.bot,
                        guild_id=server.id,
                        message_id=0
                    )

                house.name = incoming_name
                house.guild_id = server.id
                house.channel_id = incoming_channel_id
                house.min_bid_percent = self._parse_optional_float(data.get("min_bid_percent"))
                house.auction_length = self._parse_optional_float(data.get("auction_length"))
                house.reroll_interval = self._parse_optional_float(data.get("reroll_interval"))

                house = await house.upsert()

                if is_new_house:
                    house = await self._initialize_auction_house_message(house)

                retained_house_ids.add(house.id)

            for house in houses:
                if house.id not in retained_house_ids:
                    await self._delete_auction_house(house)

        else:
            schema = AuctionHouse.AuctionHouseSchema(self.bot)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            for house in houses:
                data = schema.dump(house)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output

    async def _auction_inventory_config(self, house: AuctionHouse, csv_text: str = None):
        header_mapping = {
            "id": "Item ID",
            "name": "Name",
            "description": "Description",
            "cost": "Cost",
            "category": "Category",
            "max_qty": "Max Quantity",
            "min_qty": "Min Quantity",
            "min_bid": "Min Bid"
        }

        refreshed_house = await AuctionHouse.fetch_by_id(self.bot, house.id, load_related=True)
        if not refreshed_house:
            raise StewardError("Auction house not found.")

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
            retained_item_ids = set()
            existing_items_by_id = {str(item.id): item for item in refreshed_house.items if item.id}
            existing_items_by_name = {item.name.lower(): item for item in refreshed_house.items if item.name}

            for row in rows:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                incoming_id = self._parse_optional_uuid(data.get("id"))
                incoming_name = self._normalize_csv_value(data.get("name"))

                if not incoming_name:
                    raise StewardError("Inventory item Name is required.")

                item = None
                if incoming_id:
                    item = existing_items_by_id.get(str(incoming_id))
                    # Validate that the item belongs to this house (which belongs to this guild)
                    if item and item.house_id != refreshed_house.id:
                        raise StewardError(f"Item ID {incoming_id} does not belong to auction house '{refreshed_house.name}'.")
                if not item:
                    item = existing_items_by_name.get(incoming_name.lower())

                if not item:
                    item = Item(self.bot.db, house_id=refreshed_house.id)

                item.house_id = refreshed_house.id
                item.name = incoming_name
                item.description = self._normalize_csv_value(data.get("description"))
                item.cost = self._parse_required_float(data.get("cost"), "Cost")
                item.category = self._normalize_csv_value(data.get("category"))
                item.max_qty = self._parse_optional_int(data.get("max_qty"))
                item.min_qty = self._parse_optional_int(data.get("min_qty"))
                item.min_bid = self._parse_optional_int(data.get("min_bid"))

                item = await item.upsert()
                retained_item_ids.add(item.id)

            for item in refreshed_house.items:
                if item.id not in retained_item_ids:
                    for inventory_item in list(refreshed_house.inventory):
                        if inventory_item.item_id == item.id:
                            await inventory_item.delete()
                    await item.delete()

        else:
            schema = Item.ItemSchema(self.bot.db)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            for item in refreshed_house.items:
                data = schema.dump(item)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output

    async def _auction_shelves_config(self, house: AuctionHouse, csv_text: str = None):
        header_mapping = {
            "id": "Shelf ID",
            "priority": "Priority",
            "notes": "Notes",
            "max_qty": "Max Quantity"
        }

        refreshed_house = await AuctionHouse.fetch_by_id(self.bot, house.id, load_related=True)
        if not refreshed_house:
            raise StewardError("Auction house not found.")

        if csv_text:
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
            retained_shelf_ids = set()
            existing_shelves_by_id = {str(shelf.id): shelf for shelf in refreshed_house.shelves if shelf.id}
            existing_shelves_by_priority = {shelf.priority: shelf for shelf in refreshed_house.shelves}

            for row in rows:
                data = {k: row.get(v) for k, v in header_mapping.items() if v in row}
                incoming_id = self._parse_optional_uuid(data.get("id"))
                incoming_priority = self._parse_required_int(data.get("priority"), "Priority")

                shelf = None
                if incoming_id:
                    shelf = existing_shelves_by_id.get(str(incoming_id))
                    # Validate that the shelf belongs to this house (which belongs to this guild)
                    if shelf and shelf.house_id != refreshed_house.id:
                        raise StewardError(f"Shelf ID {incoming_id} does not belong to auction house '{refreshed_house.name}'.")
                if not shelf:
                    shelf = existing_shelves_by_priority.get(incoming_priority)

                if not shelf:
                    shelf = Shelf(self.bot.db, house_id=refreshed_house.id)

                shelf.house_id = refreshed_house.id
                shelf.priority = incoming_priority
                shelf.notes = self._normalize_csv_value(data.get("notes"))
                shelf.max_qty = self._parse_required_int(data.get("max_qty"), "Max Quantity")

                shelf = await shelf.upsert()
                retained_shelf_ids.add(shelf.id)
                existing_shelves_by_priority[shelf.priority] = shelf

            for shelf in refreshed_house.shelves:
                if shelf.id not in retained_shelf_ids:
                    for inventory_item in list(refreshed_house.inventory):
                        if inventory_item.shelf_id == shelf.id:
                            await inventory_item.delete()
                    await shelf.delete()

        else:
            schema = Shelf.ShelfSchema(self.bot.db)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=header_mapping.values(), quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()

            for shelf in refreshed_house.shelves:
                data = schema.dump(shelf)
                row = {header_mapping[k]: v for k, v in data.items() if k in header_mapping}
                writer.writerow(row)

            output.seek(0)
            return output

    async def _resolve_auction_house_for_server(self, server: Server, auction_house: str) -> AuctionHouse:
        houses = [h for h in (await AuctionHouse.fetch_all(self.bot, load_related=True)) if h.guild_id == server.id]
        if not houses:
            raise StewardError("No auction houses found for this server.")

        normalized = auction_house.strip()

        try:
            incoming_id = uuid.UUID(normalized)
        except ValueError:
            incoming_id = None

        if incoming_id:
            house = next((h for h in houses if h.id == incoming_id), None)
            if house:
                return house

        house = next((h for h in houses if h.name.lower() == normalized.lower()), None)
        if house:
            return house

        raise StewardError(f"No auction house found matching '{auction_house}'.")

    async def _initialize_auction_house_message(self, house: AuctionHouse) -> AuctionHouse:
        house = await AuctionHouse.fetch_by_id(self.bot, house.id, load_related=True)
        if not house:
            raise StewardError("Auction house not found.")

        channel = house.channel
        if not isinstance(channel, discord.TextChannel):
            raise StewardError(f"Unable to resolve text channel for auction house '{house.name}'.")

        message = await channel.send(view=AuctionHouseView(house))
        house.message_id = message.id
        return await house.upsert()

    async def _delete_auction_house(self, house: AuctionHouse):
        house = await AuctionHouse.fetch_by_id(self.bot, house.id, load_related=True)
        if not house:
            return

        for inventory_item in list(house.inventory):
            await inventory_item.delete()

        for item in list(house.items):
            await item.delete()

        for shelf in list(house.shelves):
            await shelf.delete()

        await house.delete()

    @staticmethod
    def _normalize_csv_value(value):
        if value is None:
            return None
        value = str(value).strip()
        return value if value != "" else None

    def _parse_optional_uuid(self, value):
        normalized = self._normalize_csv_value(value)
        if not normalized:
            return None
        try:
            return uuid.UUID(normalized)
        except ValueError:
            raise StewardError(f"Invalid UUID value '{value}'.")

    def _parse_required_int(self, value, field_name: str):
        normalized = self._normalize_csv_value(value)
        if normalized is None:
            raise StewardError(f"{field_name} is required.")
        try:
            return int(normalized)
        except ValueError:
            raise StewardError(f"{field_name} must be an integer. Got '{value}'.")

    def _parse_optional_int(self, value):
        normalized = self._normalize_csv_value(value)
        if normalized is None:
            return None
        try:
            return int(normalized)
        except ValueError:
            raise StewardError(f"Expected integer value. Got '{value}'.")

    def _parse_required_float(self, value, field_name: str):
        normalized = self._normalize_csv_value(value)
        if normalized is None:
            raise StewardError(f"{field_name} is required.")
        try:
            return float(normalized)
        except ValueError:
            raise StewardError(f"{field_name} must be numeric. Got '{value}'.")

    def _parse_optional_float(self, value):
        normalized = self._normalize_csv_value(value)
        if normalized is None:
            return None
        try:
            return float(normalized)
        except ValueError:
            raise StewardError(f"Expected numeric value. Got '{value}'.")

