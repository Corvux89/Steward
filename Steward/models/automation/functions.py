
import random
from Steward.models.automation.exceptions import IterableTooLong, StewardValueError


MAX_ITERATION_LENGTH = 10000

def safe_range(start, stop=None, step=None):
    r = range(start, stop, step)

    if len(r) > MAX_ITERATION_LENGTH:
        raise IterableTooLong("Range is too large")
    
    return(list(r))

def typeof(inst):
    return type(inst).__name__

def rand():
    return random.random()

def randint(start, stop=None, step=1):
    return random.randrange(start, stop, step)