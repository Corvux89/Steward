"""
Utility functions for common expression evaluation patterns.
This module provides convenience wrappers for typical use cases.
"""

from typing import Any, Optional, Dict
from Steward.models.automation.context import AutomationContext
from Steward.models.automation.evaluators import evaluate_expression, StewardEvaluator
from Steward.models.automation.exceptions import StewardAutomationException


# Global evaluator instance for reuse
_default_evaluator = None


def get_default_evaluator() -> StewardEvaluator:
    """Get or create the default evaluator instance."""
    global _default_evaluator
    if _default_evaluator is None:
        _default_evaluator = StewardEvaluator()
    return _default_evaluator


def eval_with_character(expr: str, character, **extra_vars) -> Any:
    context = AutomationContext(character=character)
    return evaluate_expression(expr, context, **extra_vars)


def eval_with_player(expr: str, player, character=None, **extra_vars) -> Any:
    context = AutomationContext(player=player, character=character)
    return evaluate_expression(expr, context, **extra_vars)


def eval_numeric(expr: str, context: AutomationContext = None, default: float = 0.0, **extra_vars) -> float:
    try:
        result = evaluate_expression(expr, context, **extra_vars)
        return float(result)
    except (StewardAutomationException, ValueError, TypeError):
        return default


def eval_int(expr: str, context: AutomationContext = None, default: int = 0, **extra_vars) -> int:
    try:
        result = evaluate_expression(expr, context, **extra_vars)
        return int(result)
    except (StewardAutomationException, ValueError, TypeError):
        return default


def eval_bool(expr: str, context: AutomationContext = None, default: bool = False, **extra_vars) -> bool:
    try:
        result = evaluate_expression(expr, context, **extra_vars)
        return bool(result)
    except StewardAutomationException:
        return default


def validate_expression(expr: str, test_context: Optional[Dict[str, Any]] = None) -> tuple[bool, Optional[str]]:
    # First, try to parse it
    import ast
    try:
        ast.parse(expr, mode='eval')
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    
    # Then try to evaluate with test context
    if test_context is None:
        # Create minimal test context
        class DummyObject:
            level = 10
            activity_points = 50
            xp = 1000
            coinpurse = {"gold": 100}
        
        test_context = {"character": DummyObject()}
    
    try:
        evaluate_expression(expr, names=test_context)
        return True, None
    except StewardAutomationException as e:
        return False, e.msg
    except Exception as e:
        return False, str(e)


def batch_evaluate(expressions: Dict[str, str], context: AutomationContext, **extra_vars) -> Dict[str, Any]:
    results = {}
    for name, expr in expressions.items():
        try:
            results[name] = evaluate_expression(expr, context, **extra_vars)
        except StewardAutomationException as e:
            results[name] = None  # or could raise/log error
    
    return results


def safe_evaluate(
    expr: str,
    context: AutomationContext = None,
    default: Any = None,
    **extra_vars
) -> tuple[bool, Any]:
    try:
        result = evaluate_expression(expr, context, **extra_vars)
        return True, result
    except StewardAutomationException:
        return False, default


class ExpressionCache:
    """
    Cache for compiled expressions to improve performance.
    Useful when evaluating the same expressions repeatedly.
    """
    
    def __init__(self, max_size: int = 100):
        self.cache: Dict[str, Any] = {}
        self.max_size = max_size
        self.evaluator = StewardEvaluator()
    
    def evaluate(self, expr: str, context: AutomationContext = None, **extra_vars) -> Any:
        """
        Evaluate an expression, using cached AST if available.
        
        Note: This caches the parsed AST, but variables are still evaluated fresh each time.
        """
        # For now, just use the regular evaluator
        # A full implementation would cache the compiled AST nodes
        return evaluate_expression(expr, context, **extra_vars)
    
    def clear(self):
        """Clear the cache."""
        self.cache.clear()
