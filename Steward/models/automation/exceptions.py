class StewardAutomationException(Exception):
    def __init__(self, msg):
        super().__init__(msg)
        self.msg = msg

class InvalidExpression(StewardAutomationException):
    def __init__(self, msg, node, expr):
        super().__init__(msg)
        self.node = node
        self.expr = expr

class StewardValueError(InvalidExpression):
    pass

class LimitException(InvalidExpression):
    pass

class IterableTooLong(LimitException):
    pass