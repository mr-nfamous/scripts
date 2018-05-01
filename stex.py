
import math
import re
import string

from itertools import repeat
from random import choice
from statistics import mean, stdev
from time import perf_counter

from publicize import public
from reindent import Indenter

TEMPLATE = '''
from itertools import repeat as {repeater_name}
from time import perf_counter as {perf_ctr_name}{global_setup}

def {func_name}(): {local_setup}
    {elem_name} = {repeater_name}(1, {num_execs})
    {timer_var} = {perf_ctr_name}()
    for {elem_name} in {elem_name}:
{code}
    return {perf_ctr_name}() - {timer_var}
'''
def rand_identifier(length=10, letters=string.ascii_letters, nums=string.digits):
    assert length > 0
    tail = f"{''.join(map(choice, repeat(letters, length-1)))}"
    return choice(letters) + tail

def unique_alias(names, length=9):
    n = len(names)
    for identifier in map(rand_identifier, repeat(length)):
        if identifier not in names:
            return identifier
        #recursion error better than inifite loop with bad input
        return unique_alias(names, length)
        
class Result(float):
    def __repr__(self):
        if self < 100000:
            suf = min(5, max(int(math.log10(self)), 0))
            return f'float({round(self, 5-suf):_})'
        return f'float({int(self):_})'
    def __div__(self, other):        
        return Result(float(self)/float(other))

@public
def e(snip, *,
      global_setup=None, local_setup=None, duration=0.5, verbose=False):
    '''Approximate measurement of the operations per second of `snip`

    `snip` can be any amount of source code, and attempts will be made
    to import from the scope that called this function any names that
    were not included in `setup`

    `global_setup` is any setup to be performed in the profile global
    scope the profiler function has access to, while `local_setup`
    is inserted into the function body, before the loop.
    
    Will run for approximately `duration` seconds
    '''
    global local_code, global_code
    if global_setup is not None and not isinstance(global_setup, str):
        raise TypeError('global_setup must be a string')
    if local_setup is not None and not isinstance(local_setup, str):
        raise TypeError('local setup must be a string')
    if not isinstance(duration, float) and duration>0.025:
        raise ValueError('duration must be a float > 0.025')
    if not isinstance(snip, str):
        raise TypeError('snip must be a string representing the source code'
                        ' of the statement(s) being profiled')    
    names = dict(func_name=None, timer_var=None, perf_ctr_name=None,
                 elem_name=None, repeater_name=None)
    while any(i is None for i in names.values()):
        func_name = names['func_name'] or unique_alias(names)
        timer_var = names['timer_var'] or unique_alias(names)
        perf_ctr_name = names['perf_ctr_name'] or unique_alias(names)
        elem_name = names['elem_name'] or unique_alias(names)
        repeater_name = names['repeater_name'] or unique_alias(names)
        loc = vars()
        names = {k:(loc[k] if loc[k] not in snip else None) for k in names}
    if global_setup is None:
        global_setup = ''
    else:        
        ns = {}
        try:
            global_code = Indenter(global_setup)
            global_code.reindent(' ', 4)
            exec(str(global_code), ns)
            global_setup = str(global_code)
        except SyntaxError:
            raise SyntaxError(
                "invalid syntax in global_setup statement(s)") from None    
    global_setup = f'\n{global_setup}'
    if local_setup is None:
        local_setup = ''
    else:
        try:
            local_code = Indenter(local_setup)
            local_code.reindent(' ', 4)
            local_code.align_left()
            code = Indenter(f'{global_code}\n{local_code}')
            exec(str(code), ns)
            local_code.indent(1)
            local_setup = str(local_code)
        except SyntaxError:            
            raise SyntaxError(
                "invalid syntax in local_setup statement(s)") from None
    local_setup = f'\n{local_setup}'
    code = Indenter(snip)
    code.reindent(' ', 4)
    code.indent(2)
    imps = {}
    num_execs = 1
    while True:
        try:
            ns = {**imps}
            the_code = TEMPLATE.format_map(vars())
            if verbose:
                print(the_code)
                verbose=False
            exec(the_code, ns)
            ns[func_name]()
            break
        except NameError as x:
            name = re.search('name [\'"](?P<name>.*)[\'"]', x.args[0])
            if not name:
                raise TypeError('could not parse reqired import') from None
            name = name['name']
            try:
                exec(f'from __main__ import {name}', imps)
            except Exception as import_error:
                raise import_error from None
    while True:
        time_taken = ns[func_name]()
        if time_taken >= 0.05:
            break
        num_execs += 1 + num_execs * 2//3
        the_code = TEMPLATE.format_map(vars())
        exec(the_code, ns)
    trials = [time_taken]
    while time_taken < duration:
        trial = ns[func_name]()
        time_taken += trial
        trials.append(trial)
    trials.sort()    
    n = len(trials)
    ops = sorted(trials)
    low, *ops = ops
    while ops and stdev(ops) > 0.001:
        ops.pop()
    return Result(num_execs / mean(ops))

# A few outliers, but much less variance than timeit.autorange
##>>> e('random()', duration=2.0)
##float(14_744_203)
##>>> e('random()', duration=2.0)
##float(14_791_134)
##>>> e('random()', duration=2.0)
##float(14_392_384)
##>>> e('random()', duration=2.0)
##float(14_782_523)
##>>> e('random()', duration=2.0)
##float(14_798_640)
##>>> e('random()', duration=2.0)
##float(14_019_377)
##>>> e('random()', duration=2.0)
##float(14_593_137)
##>>> e('random()', duration=2.0)
##float(14_783_576)
##>>> e('random()', duration=2.0)
##float(14_474_003)
