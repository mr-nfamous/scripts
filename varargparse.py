
'''
Contrary to the module name, this is mostly just about dynamically creating
Python functions. However, the namesake (well, the 'argspec' class)
is important as well so I'll just leave this little description here. There's
probably something similar in inspect.py (signature) but not sure. Anyway...

Currently, if you want to have a function that can use any arbitrary kwargs, then
unless you feel like hand parsing *args to carefully select any parameters 
the function itself might need to avoid named params clashing with **kwargs, you're 
sol. Hence `argspec`, which builds a simple but efficient function that
seperates generic some positional args from *args, and then turns those
plus the leftover *args and **kws into the three-tuple:
(func_named_args, *xtra_args, **xtra_kwargs)
while having an exactly matching signature for perfect error representation.


'''

from collections import namedtuple
from operator import itemgetter as IG, attrgetter as AG
from sys import _getframe as GF
from types import CodeType, FunctionType

def namepopper(*names, defaults=None):
    names = [a for b in names for a in b.split()]
    if defaults is None:
        return lambda o: map(o.pop, names)
    assert isinstance(defaults, dict)
    defaults = (*defaults.values(),)
    return lambda o: map(o.pop, defaults)

_code_slots=('co_argcount', 'co_kwonlyargcount', 'co_nlocals',
             'co_stacksize',  'co_flags',  'co_code', 'co_consts',
             'co_names', 'co_varnames', 'co_filename',  'co_name',
             'co_firstlineno', 'co_lnotab', 'co_freevars', 'co_cellvars')

_code_attrs = AG(*_code_slots)
_code_items = IG(*_code_slots)

code_info  = namedtuple('code_info', _code_slots)
code_info.from_code = classmethod(
    lambda cls, code: cls._make(_code_attrs(code)))
code_info.compile = lambda self: CodeType(*self)

def code_as_tuple(code):
    return _code_attrs(code)

def code_as_dict(code):
    return dict(zip(_code_slots, _code_attrs(code)))

def code_from_dict(mp):
    return CodeType(*_code_items(mp))

def obj_from_code(cls, code):
    return cls(*_code_attrs(code))

code_info.from_code = classmethod(obj_from_code)

def edit_code(code, **fields):
    '''Modify out-of-place a code object using the provided fields'''
    return CodeType(*map(fields.pop, _code_slots, _code_attrs(code)))

def repl_consts(consts, repls):
    '''Replace co_consts with repls (prev_const: new_const)'''
    o = range(len(consts))
    d = dict(zip(o, consts))

    for k, v in repls.items():
        try: i = consts.index(k)
        except ValueError as ie:
            ex = TypeError("tried to replace the nonexistent func constant %r"
                           %k)
            raise ex from ie
        d[consts.index(k)] = v
    return (*[d[x] for x in o],)

def edit_closure(func, **cells):
    '''Modify out-of-place func.__closure__ by replacing the provided cells

    `cells` are name:value pairs, where `name` is the name of a free
    var (co_freevars + co_cellvars)
    '''
    closure = func.__closure__
    code    = func.__code__
    globals = func.__globals__
    cell    = None

    def setter(value):
        nonlocal cell
        cell = value

    setter = setter.__code__
    celldict = closure_as_dict(func, False)
    for k, v in cells.items():
        FunctionType(setter, globals, 'f', (), (celldict[k],))(v)

def func_from_template(name, temp, consts=None, defaults=(), closure=None,
                       globals=None):
    code = code_as_dict(temp.__code__)
    code['co_name'] = name
    if consts is not None:
        code['co_consts'] = repl_consts(code['co_consts'], consts)
    f_globals = globals or GF(1).f_globals
    return FunctionType(code_from_dict(code),
                        f_globals,
                        name,
                        defaults,
                        ())

_func_readonly_slots = ('__globals__', '__closure__')
_func_write_slots = ('__defaults__', '__code__', '__name__', '__kwdefaults__',
                     '__doc__', '__qualname__', '__dict__', '__annotations__',
                     '__module__')

_all_func_slots = _func_readonly_slots + _func_write_slots

_is_func_readonly = {*_func_readonly_slots}.__contains__

_func_attrs_w=AG(*_func_write_slots)
_func_items_w=IG(*_func_write_slots)

_func_attrs = AG(*_all_func_slots)
_func_items = IG(*_all_func_slots)

def func_as_dict(func):
    return dict(zip(_all_func_slots, _func_attrs(func)))

def func_as_dict_w(func):
    'w for writable'
    return dict(zip(_func_write_slots, _func_attrs_w(func)))

def edit_func(func,
              __globals__=None,
              __closure__=None,
              __defaults__=None,
              __code__=None,
              __name__=None,
              **kws):
    '''Modify out-of-place a function object using the provided fields'''

    repl = FunctionType(__code__ or func.__code__,
                        __globals__ or GF(1).f_globals,
                        __name__ or func.__name__,
                        __defaults__ or func.__defaults,
                        __closure__ or func.__closure__)

    for k in _func_junk:
        d = getattr(func, k)
        setattr(repl, k, kws.pop(k, d))

    assert not kws
    return repl

_edit_func_kwargs = edit_func.__code__.co_varnames[1:6]
_func_junk = {*_func_write_slots} - {*_edit_func_kwargs}
commajoin = lambda *x: ', '.join(x)
class argspec:

    '''When a func needs to be able to take any kwarg but still needs
    some args of its own, use this.

    '''

    def __call__(self, *args, **kws):
        return self.test(*args, **kws)

    def __init__(self, name, pos, **defaults):
        varnames = [a for b in [pos, defaults] for a in b]
        self.spec = namedtuple(f'{name}_argspec', varnames)
        v = commajoin(*varnames) + ', '*(len(varnames)>0)
        x = '__args__'
        y = '__kws__'
        left = f'lambda {v} *{x}, **{y}'
        rite = rite = f'("toople"({v}),  {x},   {y})'
        src = f'{left}: {rite}'
        self.src = src
        test = eval(src)
        self.test = func_from_template(
            name='test',
            temp=test,
            consts=dict(toople=self.spec),
            )

self=argspec('f', ('x',), y=10)
import dis

