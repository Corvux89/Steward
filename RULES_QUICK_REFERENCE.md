# Steward Rules Quick Reference

This document summarizes how rules, expressions, triggers, and actions work in Steward.

## Rule Lifecycle
1. A trigger fires (event or schedule).
2. `condition_expr` is evaluated; if false, the rule is skipped.
3. Actions run in the order they appear (single dict or a list of dicts).
4. For scheduled rules, `last_run_ts` is updated after execution.

## Triggers
- `member_join`, `member_leave`, `level_up`, `new_character`, `log`, `scheduled`

## Context Available in Expressions
Expressions and templates can access the automation context:
- `server`: Guild/server object
- `player`: Player object (may be None)
- `character`: Character object (may be None)
- `log`: StewardLog object (may be None)
- `ctx`: Discord interaction/command context (may be None)
- `rule`: The current rule object

## Condition Expressions (`condition_expr`)
- Evaluated with `eval_bool`; must return truthy/falsey.
- Examples:
  - `character.level >= 5`
  - `server.currency_limit_expr is not None`
  - `player.command_count > 10 if player else False`

## Template Expressions in Messages
- Message content and embed fields support `{...}` expressions evaluated with the same context.
- Examples:
  - `"Player: {player.mention if player else 'Unknown'}"`
  - `"XP: {log.xp if log else 0}"`

## Scheduling
- `schedule_cron` supports standard 5-part cron: `minute hour day month day_of_week`.
- Shortcuts (loose timing, run once per period): `@hourly`, `@daily`, `@midnight`, `@weekly`, `@monthly`, `@yearly`, `@annually`.
  - Shortcut behavior is period-based (e.g., @hourly runs once per hour, not just at minute 0).
- Standard cron uses exact matches (e.g., `0 9 * * 1-5` for weekdays at 09:00 UTC).

## Actions
Actions are dicts; you can provide a single dict or a list to run sequentially.

### `message`
Fields:
- `channel_id` (optional): falls back to `ctx.channel` if omitted
- `content`: text with templates allowed
- `embed` (optional):
  - `title`, `description`, `color`
  - `fields`: list of `{name, value, inline}` (templates allowed)
  - `footer`, `thumbnail`

### `reward`
- Uses StewardLog.create to reward currency/xp.
- Fields: `activity`, `currency`, `xp`, `notes`.

### `reset_all_limited_xp`
- Sets `character.limited_xp = 0` for all server characters and upserts.

### `reset_all_limited_currency`
- Sets `character.limited_currency = 0` for all server characters and upserts.

### `reset_activity_points`
- Sets `character.activity_points = 0` for all server characters and upserts.

## Example: Message + Resets (scheduled hourly)
```json
{
  "name": "Hourly Reset",
  "trigger": "scheduled",
  "enabled": true,
  "priority": 1,
  "schedule_cron": "@hourly",
  "action_data": [
    {
      "type": "message",
      "channel_id": 1465371354340524205,
      "content": "Reset done"
    },
    {"type": "reset_all_limited_xp"},
    {"type": "reset_all_limited_currency"},
    {"type": "reset_activity_points"}
  ]
}
```

## CSV Columns (import/export)
- `Name`
- `Trigger`
- `Enabled` (true/false)
- `Condition Expression`
- `Priority`
- `Schedule Cron` (empty for non-scheduled)
- `Action Data (JSON)` (stringified JSON object or array)

Example CSV row:
```
"Hourly Reset","scheduled",true,"",1,"@hourly","","[{""type"":""message"",""channel_id"":1465371354340524205,""content"":""Reset done""},{""type"":""reset_all_limited_xp""},{""type"":""reset_all_limited_currency""},{""type"":""reset_activity_points""}]"
```

---

# Object Reference

## Player
A Discord member wrapper accessible in rule expressions.

### Safe Attributes (Available in Expressions)
- **`id`** (`int`): Discord user ID.
- **`guild_id`** (`int`): Guild ID.
- **`campaign`** (`str | None`): Optional campaign identifier.
- **`primary_character`** → `Character`: Player's primary character.
- **`highest_level_character`** → `Character`: Character with highest level.
- **`mention`** (`str`): User mention string.
- **`name`** (`str`): Discord username.
- **`display_name`** (`str`): Nickname or username.
- **`avatar`**: Avatar object.
- **`staff_points`** (`int`): Staff contribution counter.

---

## Character
A persistent player-controlled character record.

### Safe Attributes (Available in Expressions)
- **`id`** (`uuid.UUID`): Primary key.
- **`name`** (`str`): Character name.
- **`player_id`** (`int`): Owning player ID.
- **`guild_id`** (`int`): Owning guild ID.
- **`level`** (`int`): Character level.
- **`xp`** (`int`): Total XP earned.
- **`currency`** (`Decimal`): Currency balance.
- **`primary_character`** (`bool`): Player's primary flag.
- **`nickname`** (`str`): Display nickname.
- **`activity_points`** (`int`): Activity point tally.
- **`mention`** (`str`): Character nickname or name.

---

## NPC
A guild-scoped non-player character.

### Safe Attributes (Available in Expressions)
- **`id`** (`uuid.UUID`): Primary key.
- **`name`** (`str`): NPC name.
- **`guild_id`** (`int`): Owning guild ID.
- **`level`** (`int`): NPC level.
- **`active`** (`bool`): Whether NPC is active.

---

## Server
A guild wrapper with Steward configuration.

### Safe Attributes (Available in Expressions)
- **`id`** (`int`): Guild ID.
- **`max_level`** (`int`): Maximum character level.
- **`currency_label`** (`str`): Display label for currency (e.g., "gp").
- **`staff_role_id`** (`int | None`): Role ID marking server staff.

### Safe Methods (Available in Expressions)
- **`get_xp_for_level(level)`** → `int`: Get XP required for a level.
- **`get_level_for_xp(xp)`** → `int`: Get character level for given XP.
- **`get_activity_for_points(points)`**: Get activity point threshold.
- **`max_characters(player)`** → `int | None`: Evaluate max character slot expression.
- **`currency_limit(player, character)`** → `int | None`: Evaluate currency cap expression.
- **`xp_limit(player, character)`** → `int | None`: Evaluate XP cap expression.
- **`xp_global_limit(player, character)`** → `int | None`: Evaluate global XP cap expression.
- **`get_tier_for_level(level)`** → `int`: Get tier for a level.

---

## StewardLog
A transactional log entry; exposed in certain rule triggers.

### Safe Attributes (When Available)
- **`id`** (`uuid.UUID`): Primary key.
- **`author_id`** (`int`): Initiator user ID.
- **`player_id`** (`int`): Affected player ID.
- **`guild_id`** (`int`): Guild scope.
- **`event`** (`LogEvent`): Event type.
- **`character_id`** (`uuid.UUID | None`): Character affected (if any).
- **`activity_id`** (`uuid.UUID | None`): Associated activity.
- **`currency`** (`Decimal`): Currency delta.
- **`xp`** (`Decimal | int`): XP delta.
- **`notes`** (`str | None`): Log notes.
- **`invalid`** (`bool`): Invalidation flag.
- **`created_ts`** (`datetime`): Creation timestamp (UTC).
- **`server`** (`Server`): Resolved server object.
- **`player`** (`Player`): Resolved player object.
- **`author`** (`Player | discord.User`): Resolved author object.
- **`character`** (`Character | None`): Resolved character object.

---

## StewardRule
An automation rule; exposed in expression context.

### Safe Attributes (When Available)
- **`name`** (`str`): Rule name.
- **`trigger`** (`RuleTrigger`): Event name.

## Tips
- Use lists for multiple actions; they run in order.
- Use templates `{...}` inside message content/embed fields to pull data from context.
- For shortcuts, remember they run once per period (hour/day/week/month/year).
- For precise times, prefer full cron expressions.
- Keep `condition_expr` simple and defensive when optional context objects may be None.
