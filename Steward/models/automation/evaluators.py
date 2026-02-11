import ast
import time
import operator

from math import ceil, floor, sqrt
from typing import Any, Dict, Optional
from Steward.models.automation.functions import rand, randint, typeof
from Steward.models.automation.exceptions import InvalidExpression, StewardValueError, LimitException
from Steward.models.automation.context import AutomationContext
from Steward.models.objects.patrol import Patrol

class SafeObject:
    """Base class for safe wrapper objects that restricts access to dangerous methods"""
    _allowed_attrs = set()  # Override in subclasses
    _allowed_methods = set()  # Override in subclasses
    
    def __init__(self, obj):
        object.__setattr__(self, '_obj', obj)
    
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(f"Access to private attribute '{name}' is not allowed")
        
        allowed = self._allowed_attrs | self._allowed_methods
        if name not in allowed:
            raise AttributeError(f"Access to attribute '{name}' is not allowed")
        
        value = getattr(self._obj, name)
        
        # If it's a method that's not in allowed_methods, don't return it
        if callable(value) and name not in self._allowed_methods:
            raise AttributeError(f"Method '{name}' is not callable in expressions")
        
        return value
    
    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            raise AttributeError("Cannot set attributes on safe objects")


class SafeCharacter(SafeObject):
    """Safe wrapper for Character objects - read-only access"""
    _allowed_attrs = {
        'id', 'name', 'player_id', 'guild_id', 'level', 'xp',
        'currency', 'primary_character', 'nickname', 'activity_points', 'mention'
    }
    _allowed_methods = set()  


class SafePlayer(SafeObject):
    """Safe wrapper for Player objects - read-only access"""
    _allowed_attrs = {
        'id', 'guild_id', 'campaign', 'primary_character', 'highest_level_character', 'mention', 'name', 'display_name', 
        'avatar', 'staff_points', 'roles', 'active_characters', 'display_avatar'
    }
    _allowed_methods = set()

    @property
    def highest_level_character(self):
        return SafeCharacter(getattr(self._obj, "highest_level_character"))
    
    @property
    def primary_character(self):
        return SafeCharacter(getattr(self._obj, "primary_character"))
    
    @property
    def active_characters(self):
        return [SafeCharacter(c) for c in getattr(self._obj, "active_characters")]

    @property
    def roles(self):
        return [role.id for role in getattr(self._obj, 'roles', [])]


class SafeServer(SafeObject):
    """Safe wrapper for Server objects - read-only access"""
    _allowed_attrs = {
        'id', 'max_level', 'currency_label', 'staff_role_id'
    }
    _allowed_methods = {
        'get_xp_for_level', 'get_level_for_xp', 'get_activity_for_points', 'max_characters',
        'currency_limit', 'xp_limit', 'xp_global_limit', 'get_tier_for_level'
    }

class SafeNPC(SafeObject):
    """Safe wrapper for NPC objects - read-only access"""
    _allowed_attrs = {
        'id', 'name', 'guild_id', 'level', 'active'
    }
    _allowed_methods = set()  

class SafeLog(SafeObject):
    _allowed_attrs = {
        'id', 'author', 'player', 'event', 'activity', 'currency', 'xp', 'notes',
        'invalid', 'character', 'original_xp', 'original_currency', 'epoch_time',
        'created_ts'
    }

    _allowed_methods = set()

    @property
    def player(self):
        return SafePlayer(getattr(self._obj, "player"))
    
    @property
    def event(self):
        event = getattr(self._obj, "event")
        if not event:
            return None

        return getattr(event, "name")
    
    @property
    def author(self):
        return SafePlayer(getattr(self._obj, "author"))
    
    @property
    def character(self):
        return SafeCharacter(getattr(self._obj, "character"))
    
class SafePatrol(SafeObject):
    _allowed_attrs = {
        "id", "notes", "created_ts", "end_ts", "outcome",
        "characters", "character_ids"
    }

    @property
    def characters(self):
        return [SafeCharacter(c) for c in getattr(self._obj, "characters")]


def safe_getattr(obj, attr, default=''):
    """Safely get an attribute from an object, returning default if obj is None or attr doesn't exist"""
    if obj is None:
        return default
    return getattr(obj, attr, default)

DEFAULT_BUILTINS = {
    "floor": floor,
    "ceil": ceil,
    "round": round,
    "len": len,
    "max": max,
    "min": min,
    "enumerate": enumerate,
    "range": range,
    "sqrt": sqrt,
    "sum": sum,
    "any": any,
    "all": all,
    "abs": abs,
    "time": time.time,
    "typeof": typeof,
    "rand": rand,
    "randint": randint,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "getattr": safe_getattr
}

class StewardConfig:
    def __init__(
            self,
            max_const_len=200_000,
            max_loops=10_000,
            max_statements=100_000,
            max_power_base=1_000_000,
            max_power=1_000,
            disallow_prefixes=None,
            disallow_methods=None,
            max_int_size=64
            ):
        
        disallow_prefixes = ["_", "func_"] if not disallow_prefixes else disallow_prefixes
        disallow_methods = ["format", "format_map", "mro", "tb_frame", "gi_frame", "ag_frame", "cr_frame", "exec"] if not disallow_methods else disallow_methods

        self.max_const_len = max_const_len
        self.max_loops = max_loops
        self.max_statements = max_statements
        self.max_power_base = max_power_base
        self.max_power = max_power
        self.max_int_size = max_int_size
        self.min_int = -(2 ** (max_int_size-1))
        self.max_int = (2 ** (max_int_size-1)) - 1
        self.disallow_prefixes = disallow_prefixes
        self.disallow_methods = disallow_methods


class StewardEvaluator(ast.NodeVisitor):    
    def __init__(self, config: Optional[StewardConfig] = None, builtins: Optional[Dict[str, Any]] = None):
        self.config = config or StewardConfig()
        self.builtins = builtins or DEFAULT_BUILTINS.copy()
        self.statement_count = 0
        self.loop_count = 0
        
        # Supported operators
        self.operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: self._safe_pow,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }
        
        # Comparison operators
        self.comp_operators = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
            ast.Is: operator.is_,
            ast.IsNot: operator.is_not,
            ast.In: lambda x, y: x in y,
            ast.NotIn: lambda x, y: x not in y,
        }
        
        # Boolean operators
        self.bool_operators = {
            ast.And: all,
            ast.Or: any,
        }
    
    def _safe_pow(self, base, exp):
        """Safe power operation with limits"""
        if abs(base) > self.config.max_power_base:
            raise LimitException(
                f"Power base {base} exceeds maximum {self.config.max_power_base}",
                None, ""
            )
        if abs(exp) > self.config.max_power:
            raise LimitException(
                f"Power exponent {exp} exceeds maximum {self.config.max_power}",
                None, ""
            )
        return base ** exp
    
    def _check_statement_limit(self):
        """Check if we've exceeded the statement limit"""
        self.statement_count += 1
        if self.statement_count > self.config.max_statements:
            raise LimitException(
                f"Expression exceeded maximum statements ({self.config.max_statements})",
                None, ""
            )

    def _check_loop_limit(self):
        """Check if we've exceeded the loop limit"""
        self.loop_count += 1
        if self.loop_count > self.config.max_loops:
            raise LimitException(
                f"Expression exceeded maximum loops ({self.config.max_loops})",
                None, ""
            )
    
    def eval(self, expr: str, names: Optional[Dict[str, Any]] = None) -> Any:
        names = names or {}
        self.statement_count = 0
        self.loop_count = 0
        
        try:
            node = ast.parse(expr, mode='eval')
        except SyntaxError as e:
            raise InvalidExpression(f"Syntax error in expression: {e}", None, expr)
        
        # Merge builtins and names
        self.names = {**self.builtins, **names}
        
        try:
            return self.visit(node.body)
        except RecursionError:
            raise LimitException("Expression exceeded maximum recursion depth", None, expr)
    
    def visit_Expression(self, node):
        return self.visit(node.body)
    
    def visit_Constant(self, node):
        self._check_statement_limit()
        value = node.value
        
        if isinstance(value, (str, bytes)) and len(value) > self.config.max_const_len:
            raise LimitException(
                f"Constant length {len(value)} exceeds maximum {self.config.max_const_len}",
                node, ""
            )
        
        return value
    
    def visit_Num(self, node):
        return node.n
    
    def visit_Str(self, node):
        return node.s
    
    def visit_Name(self, node):
        self._check_statement_limit()
        
        if node.id not in self.names:
            raise StewardValueError(f"Name '{node.id}' is not defined", node, "")
        
        return self.names[node.id]
    
    def visit_Attribute(self, node):
        self._check_statement_limit()
        
        obj = self.visit(node.value)
        attr = node.attr
        
        # Check for disallowed prefixes
        for prefix in self.config.disallow_prefixes:
            if attr.startswith(prefix):
                raise StewardValueError(
                    f"Access to attribute '{attr}' is not allowed",
                    node, ""
                )
        
        # Check for disallowed methods
        if attr in self.config.disallow_methods:
            raise StewardValueError(
                f"Access to method '{attr}' is not allowed",
                node, ""
            )
        
        try:
            return getattr(obj, attr)
        except AttributeError:
            raise StewardValueError(
                f"Object has no attribute '{attr}'",
                node, ""
            )
    
    def visit_BinOp(self, node):
        self._check_statement_limit()
        
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = self.operators.get(type(node.op))
        
        if op is None:
            raise InvalidExpression(
                f"Operator {type(node.op).__name__} is not supported",
                node, ""
            )
        
        return op(left, right)
    
    def visit_UnaryOp(self, node):
        self._check_statement_limit()
        
        operand = self.visit(node.operand)
        
        if isinstance(node.op, ast.Not):
            return not operand
        
        op = self.operators.get(type(node.op))
        if op is None:
            raise InvalidExpression(
                f"Unary operator {type(node.op).__name__} is not supported",
                node, ""
            )
        
        return op(operand)
    
    def visit_Compare(self, node):
        self._check_statement_limit()
        
        left = self.visit(node.left)
        
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            comp_op = self.comp_operators.get(type(op))
            
            if comp_op is None:
                raise InvalidExpression(
                    f"Comparison operator {type(op).__name__} is not supported",
                    node, ""
                )
            
            if not comp_op(left, right):
                return False
            
            left = right
        
        return True
    
    def visit_BoolOp(self, node):
        self._check_statement_limit()

        if isinstance(node.op, ast.And):
            last_value = None
            for value_node in node.values:
                last_value = self.visit(value_node)
                if not last_value:
                    return last_value
            return last_value
        elif isinstance(node.op, ast.Or):
            last_value = None
            for value_node in node.values:
                last_value = self.visit(value_node)
                if last_value:
                    return last_value
            return last_value
        else:
            raise InvalidExpression(
                f"Boolean operator {type(node.op).__name__} is not supported",
                node, ""
            )
    
    def visit_IfExp(self, node):
        self._check_statement_limit()
        
        test = self.visit(node.test)
        
        if test:
            return self.visit(node.body)
        else:
            return self.visit(node.orelse)
    
    def visit_Call(self, node):
        self._check_statement_limit()
        
        func = self.visit(node.func)
        args = [self.visit(arg) for arg in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords}
        
        if not callable(func):
            raise StewardValueError(f"'{func}' is not callable", node, "")
        
        return func(*args, **kwargs)
    
    def visit_List(self, node):
        self._check_statement_limit()
        return [self.visit(elt) for elt in node.elts]
    
    def visit_Tuple(self, node):
        self._check_statement_limit()
        return tuple(self.visit(elt) for elt in node.elts)
    
    def visit_Dict(self, node):
        self._check_statement_limit()
        return {
            self.visit(k): self.visit(v)
            for k, v in zip(node.keys, node.values)
        }
    
    def visit_Subscript(self, node):
        self._check_statement_limit()
        
        obj = self.visit(node.value)
            
        key = self.visit(node.slice)
        
        try:
            return obj[key]
        except (KeyError, IndexError, TypeError) as e:
            raise StewardValueError(f"Subscript error: {e}", node, "")

    def _assign_target(self, target, value, names: Dict[str, Any]):
        if isinstance(target, ast.Name):
            names[target.id] = value
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            if not isinstance(value, (list, tuple)):
                raise InvalidExpression("Cannot unpack non-iterable in comprehension", target, "")
            if len(target.elts) != len(value):
                raise InvalidExpression("Unpack mismatch in comprehension", target, "")
            for elt, item in zip(target.elts, value):
                self._assign_target(elt, item, names)
            return
        raise InvalidExpression("Unsupported comprehension target", target, "")

    def _eval_with_names(self, node, names: Dict[str, Any]):
        original_names = self.names
        self.names = names
        try:
            return self.visit(node)
        finally:
            self.names = original_names

    def _eval_comprehension(self, generators, eval_elt, names: Dict[str, Any]):
        if not generators:
            yield eval_elt(names)
            return

        gen = generators[0]
        iter_obj = self._eval_with_names(gen.iter, names)
        for item in iter_obj:
            self._check_loop_limit()
            next_names = names.copy()
            self._assign_target(gen.target, item, next_names)
            if gen.ifs:
                if not all(self._eval_with_names(test, next_names) for test in gen.ifs):
                    continue
            yield from self._eval_comprehension(generators[1:], eval_elt, next_names)

    def visit_GeneratorExp(self, node):
        self._check_statement_limit()
        base_names = self.names.copy()

        def eval_elt(local_names):
            return self._eval_with_names(node.elt, local_names)

        return self._eval_comprehension(node.generators, eval_elt, base_names)

    def visit_ListComp(self, node):
        self._check_statement_limit()
        return list(self.visit_GeneratorExp(node))
    
    def generic_visit(self, node):
        raise InvalidExpression(
            f"Expression type {type(node).__name__} is not supported",
            node, ""
        )


def evaluate_expression(
    expr: str,
    context: Optional[AutomationContext] = None,
    **extra_vars
) -> Any:
    from Steward.models.objects.character import Character
    from Steward.models.objects.player import Player
    from Steward.models.objects.servers import Server
    from Steward.models.objects.npc import NPC
    from Steward.models.objects.log import StewardLog
    
    evaluator = StewardEvaluator()
    
    names = {}
    if context:
        context_dict = {}
        for key, value in context.__dict__.items():
            if not key.startswith('_'):
                context_dict[key] = value
        
        # Wrap all objects
        for key, value in context_dict.items():
            if value is None:
                names[key] = None
            elif isinstance(value, Character):
                names[key] = SafeCharacter(value)
            elif isinstance(value, Player):
                names[key] = SafePlayer(value)
            elif isinstance(value, Server):
                names[key] = SafeServer(value)
            elif isinstance(value, NPC):
                names[key] = SafeNPC(value)
            elif isinstance(value, StewardLog):
                names[key] = SafeLog(value)
            elif isinstance(value, Patrol):
                names[key] = SafePatrol(value)
            else:
                names[key] = value
    
    names.update(extra_vars)
    
    return evaluator.eval(str(expr), names )