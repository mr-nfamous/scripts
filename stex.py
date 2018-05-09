
i
import math
import re
import string

from itertools import repeat
from random import choice
from statistics import mean, stdev
from time import perf_counter

from publicize import public
from reindent import Indenter
RANDOMIZE_IDS = True
TEMPLATE = '''
from itertools import repeat as {repeater_name}
from time import perf_counter as {perf_ctr_name}{global_setup}

def {func_name}(): {local_setup}
{imp_setup}
    {elem_name} = {repeater_name}(1, {num_execs})
    {timer_var} = {perf_ctr_name}()
    for {elem_name} in {elem_name}:
{code}
    return {perf_ctr_name}() - {timer_var}
'''
LETTERS = string.ascii_letters
NUMBERS = string.digits + '_'
def rand_identifier(length, letters=LETTERS, nums=NUMBERS):
    assert length > 0
    tail = f"{''.join(map(choice, repeat(letters, length-1)))}"
    return choice(letters) + tail

def unique_alias(names, length):
    n = len(names)
    for identifier in map(rand_identifier, repeat(length)):
        if identifier not in names:
            return identifier
        #easier to spot a recursion error with all of the looping in
        #this file...
        return unique_alias(names, length)

class Result(float):
    def __repr__(self):
        if self < 100000:
            suf = min(5, max(int(math.log10(self)), 0))
            return f'float({round(self, 5-suf):_})'
        return f'float({int(self):_})'
    def __div__(self, other):
        return Result(float(self)/float(other))

def randomize_names(names, length=10):
    if not all(k.isidentifier() for k in names):
        raise ValueError('names to ranomize must be identifiers')
    if any(v is not None or (isinstance(v,str) and not v.isidentifier())
           for v in names.values()):
        raise ValueError('aliases must be an identifier')
    hasnames = set(names.values())
    nonames = {k for k,v in names.items() if v is None}
    while nonames:
        alias = name = nonames.pop()
        while alias in names:
            alias = unique_alias(hasnames, length)
        names[name] = alias
        hasnames.add(alias)

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
    randomize_names(names)
    func_name = names['func_name']
    timer_var = names['timer_var']
    perf_ctr_name = names['perf_ctr_name']
    elem_name = names['elem_name']
    repeater_name = names['repeater_name']
    ns = {}
    imp_setup = ''
    if global_setup is None:
        global_setup = ''
        global_code = ''
    else:
        try:
            global_code = Indenter(global_setup)
            global_code.reindent(' ', 4)
            exec(str(global_code), ns)
            global_setup = str(global_code)
        except SyntaxError:
            raise SyntaxError(
                "invalid syntax in global setup statement(s)") from None
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
                "invalid syntax in local setup statement(s)") from None
    local_setup = f'\n{local_setup}'
    code = Indenter(snip)
    code.reindent(' ', 4)
    code.indent(2)
    num_execs = 1
    implist = []
    used_names = set(names.values())
    while True:
        try:
            the_code = TEMPLATE.format_map(vars())
            if verbose:
                print(the_code)
                verbose=False
            exec(the_code, ns)
            ns[func_name]()
            break
        except NameError as x:
            name = re.search('name [\'"](?P<name>.*)[\'"]', x.args[0])['name']
            # if the there are quandrillions of universes with trillions of
            # civilizations that develped both english and python, would this
            # condition ever actually occur?
            for k, v in (*names.items(),):                
                a = v
                while a == name:
                    a = unique_alias(used_names)
                used_names.remove(v)
                used_names.add(a)
                names[k] = vars()[k] = a                    
            try:               
                exec(f'from __main__ import {name}', {})
                implist.append(f'    from __main__ import {name}')
                imp_setup = '\n'.join(implist)
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
    lo, *ops = trials
    # seems like 95% of results are within 3% of each other
    # but then one will be 10% slower than usual, so just remove
    # abnormally slow trials (not sure if this really accomplishes anything)
    while len(ops)>1 and stdev(ops) > 0.001:
        ops.pop()
    return Result(num_execs / mean(ops))


