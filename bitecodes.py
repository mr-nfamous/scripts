
'''Bitecodes - dynamic modification of python bytecode

'''
import builtins as _builtins
import ctypes
import dis
import enum

from collections import namedtuple
from collections.abc import Mapping
from copy import copy as _copy, deepcopy as _deepcopy
from functools import lru_cache, reduce
from keyword import iskeyword
from operator import attrgetter, truth, or_
from types import FunctionType, CodeType, SimpleNamespace

from publicize import *

CellType = type((lambda __class__: (lambda: super).__closure__[0])(''))

_pycell_new = ctypes.pythonapi.PyCell_New
_pycell_new.argtypes = (ctypes.py_object,)
_pycell_new.restype = ctypes.py_object
_pycell_set = ctypes.pythonapi.PyCell_Set
_pycell_set.argtypes = (ctypes.py_object, ctypes.py_object)

is_cell = CellType.__instancecheck__
is_tuple = tuple.__instancecheck__
is_func = FunctionType.__instancecheck__
is_str = str.__instancecheck__
is_code = CodeType.__instancecheck__
is_function = FunctionType.__instancecheck__
is_dict = dict.__instancecheck__
is_mapping = Mapping.__instancecheck__

code_params = ('co_argcount', 'co_kwonlyargcount', 'co_nlocals', 'co_stacksize',
               'co_flags', 'co_code', 'co_consts', 'co_names',  'co_varnames',
               'co_filename', 'co_name', 'co_firstlineno', 'co_lnotab',
               'co_freevars', 'co_cellvars')

code_init_args = attrgetter(*code_params)
CodeInfo = namedtuple('CodeInfo', [i[3:] for i in code_params])

get_class = object.__dict__['__class__'].__get__

@lru_cache(512)
def descriptor_getter(cls):
    getters = {}
    for k, v in type.__dict__['__dict__'].__get__(cls).items():
        if hasattr(v, '__get__'):
            getters[k] = v.__get__
    def getter(attr, ob):
        return getters[attr](ob)
    return getter

def tuple_copy(tup):
    return (*tup,)

@public
def descriptor_getattr(ob, attr):
    'Get unbound descriptor instance from an instance'
    getter = descriptor_getter(get_class(ob))
    try:
        return getter(attr, ob)
    except KeyError:
        error = AttributeError(f'type object {get_class(ob).__name__!r} '
                               f'has no descriptor {attr!r}')
    raise error

get_func_attr = descriptor_getter(FunctionType)

@public
def get_code_info(f):
    if is_code(f):
        co = f
    elif is_func(f):
        co = f.__code__
    else:
        raise TypeError('argument must be a function or code object')
    return CodeInfo(*code_init_args(co))

@lru_cache(64)
def build_class_cell(__class__):
    '''There should be only one __class__ cell per class'''
    if not isinstance(__class__, type):
        raise TypeError('can only build cell object for classes.')
    for attr, val in __class__.__dict__.items():
        closure = getattr(val, '__closure__', None)
        if closure is not None:
            for cell in closure:
                if cell.cell_contents is __class__:
                    return cell
    return (lambda: __class__).__closure__[0]

def deepcopy_cell(cell):
    contents = _deepcopy(cell.cell_contents)

    new_cell = (lambda: contents).__closure__[0]
    return new_cell

content_getter = attrgetter('cell_contents')

def deepcopy_cell(cell):
    if not is_cell(cell):
        raise TypeError('cell to deepcopy must be a cell object')
    contents = _deepcopy(cell.cell_contents)
    return (lambda: contents).__closure__[0]

def deepcopy_closure(closure):
    if closure is None:
        return
    if not is_tuple(closure)or not all(map(is_cell, closure)):
        raise TypeError('closure must be a tuple of cell objects or None')
    return (*map(deepcopy_cell, closure),)

@public
def view_closure_cells(ob):
    if not is_func(ob):
        raise TypeError('ob must be a function')
    closure = ob.__closure__
    if closure is None:
        return
    contents = map(attrgetter('cell_contents'), closure)
    return SimpleNamespace(**dict(zip(ob.__code__.co_freevars, contents)))

class CoFlag(enum.IntFlag):
    OPTIMIZED = 1
    NEWLOCALS = 2
    VARARGS = 4
    VARKEYWORDS = 8
    NESTED = 16
    GENERATOR = 32
    NOFREE = 64
    COROUTINE = 128
    ITERABLE_COROUTINE = 256
    ASYNC_GENERATOR = 512

public_constants(**CoFlag.__members__)
is_co_flag = CoFlag.__instancecheck__
_get_co_flags = type.__dict__['__flags__'].__get__

@public
def is_heap_type(ob):
    '`ob` is a pure Python class'
    return truth(isinstance(ob, type) and _get_co_flags(ob) & 0x200)

@public
def get_co_flags(flags):
    if is_func(flags):
        flags = flags.__code__.co_flags
    elif is_co_flag(Flags):
        return flags
    elif is_code(flags):
        flags = flags.co_flags
    elif not hasattr(flags, '__index__'):
        raise TypeError('cannot parse co_flags from {type(flags).__name_} obj')
    # use __index__ so any int like object can represent flags
    else:
        flags = flags.__index__()
    return reduce(or_, (i for i in CoFlag if flags&i))

@public
def update_code(ob, **kws):
    '''Get new code object based on `ob` with replacements from **kws'''
    if isinstance(ob, CodeInfo):
        info = code
    elif isinstance(ob, (CodeType, FunctionType)):
        info = get_code_info(ob)
    elif not ob:
        info = CodeInfo(**kws)
    else:
        info = CodeInfo(*ob.__code__)
    return CodeType(*info._replace(**kws))

@public
def rebuild_func(
    func,
    cls=None,
    *wrappers,
    
    defaults_copy=None,
    kwdefaults_copy=None,
    dict_copy=None,
    closure_copy=None,

    global_ns=None,
    name=None,
    qualname=None,
    
    module=False,
    doc=False,
    annotations=False,
    ):
    """Create a copy of `func` that can be used as a method by any `cls`

    The main perk is giving a `cls` the ability to use *any* Python
    `function` as a bound method, regardless of where it was defined.
    In other words, it doesn't matter if a function was defined in the
    global scope, another module, or in the body of another class.
    Most importantly, functions that use zero-argument super will behave
    exactly the same as if they had been defined in `cls`.

    Unfortunately, there is one limitation.
    Wrapped functions not defined in the scope of a class body will not
    be able to use zero argument super. If they are wrapped *after*
    being bound with this function, they should have no problem working

    For convenience, any *wrappers provided will be applied after binding
    in the same order as decorator syntax, top to bottom or right to left
    ie. wrappers *(a, b ,c) will be equivalent to a(b(c(func)))

    There are nearly limitless uses for this black magic, but some
    good examples are the ability to make true deepcopies of functions,
    changing default/kwonly defaults, and tricking functions into using
    global references to objects not in the module it was defined in.

    To simplify the application of making true deepcopies of functions,
    which requires deepcopying of the original function's mutable
    attributes: __defaults__, __kwdefaults__, __dict__, and __closure__,
    the arguments `defaults_copy`, `kwdefaults_copy, `dict_copy`, and
    `closure_copy`, respectively, accept a callable that takes a single
    argument (the object to be copied) and returns an object of the
    same type (and length if applicable) to the original.
    If `defaults_copy` and `kwdefaults_copy` return None, the new
    function will no longer have default values.

    Otherwise, shallow copies of __defaults__, __kwdefaults__, and
    __dict__ are used, along with a deepcopy of __closure__.
    
    Parameters:

    :: `defaults_copy`
        called as defaults_copy(func.__defaults__) to replace
        `func.__defaults__`, the attribute that stores a tuple
        containing the default values of positional arguments.
        
        Removes default positional arguments entirely if it returns None

    :: `kwdefaults_copy`
        called as kwdefaults_copy(func.__kwdefaults__) to replace
        `func.__kwdefaults__`, the attribute that stores a mapping
        containing the default values of keyword only arguments.

        Removes default kwonly arguments entirely if it returns None
        
    :: `dict_copy`
        called as dict_copy(func.__dict__) to replace `func.__dict__`

    :: `closure_copy`
        called as closure_copy(func.__closure__) to replace
        `func.__closure__`, the attribute that stores references
        to any nonlocal names used by `func`

    :: `global_ns`
        used to replace func.__globals__
        
        Will raise NameError if it doesn't contain all global references
        used by `func`.
        
    :: `name`
        a string that replaces func.__name__

    :: `qualname`
        if None, will generate a new __qualname__ automatically,
        which depends on the values in `name`, `func`, and `cls`

        Otherwise, a string

    :: `module`
        can be any type and is used to replace `func.__module__`

    :: `doc`
        can be any type and is used to replace `func.__doc__`
        
    :: `annotations`
        None to clear or mapping to replace `func.__annotations__`

        By default is a shallow copy of `func.__annotations__`
    """

    # validate func
    if not is_func(func):
        raise TypeError('func must be function object')
    else:
        f = func

    # validate cls
    if cls is None:
        class_was_not_none = False
    elif not is_heap_type(cls):
        raise TypeError('cls must be None or a Python class')
    else:
        class_was_not_none = True

    # validate defaults_copy
    defaults = f.__defaults__
    if defaults_copy is None:
        defaults = None if defaults is None else tuple_copy(defaults)
    elif not callable(defaults_copy):
        raise TypeError('defaults_copy must be a callable')
    else:
        defaults = defaults_copy(defaults)
    
    # validate kwdefaults_copy
    kwdefaults = f.__kwdefaults__
    if kwdefaults_copy is None:
        kwdefaults = None if kwdefaults is None else {**kwdefaults}
    elif not callable(kwdefaults_copy):
        raise TypeError('kwdefaults_copy must be a callable')
    else:
        kwdefaults = kwdefaults_copy(kwdefaults)
    
    # validate dict_copy
    new_dict = descriptor_getattr(f, '__dict__')
    if dict_copy is None:
        new_dict = {**new_dict}
    elif not callable(dict_copy):
        raise TypeError('dict_copy must be a callable')
    else:
        new_dict = dict_copy(new_dict)
    
    # validate closure_copy
    closure = f.__closure__
    if closure_copy is None:
        if is_tuple(closure):
            closure = deepcopy_closure(closure)
    elif not callable(closure_copy):
        raise TypeError('closure_copy must be a callable')
    else:
        closure = closure_copy(closure)
    
    # validate name
    if name is None:
        name = f.__name__
    elif not is_str(name):
        raise TypeError('function __name__ must be a string')

    # validate qualname
    if qualname is None:
        qualname = f'{cls.__name__}.{name}' if class_was_not_none else name
    elif not is_str(qualname):
        raise TypeError('function __qualname__ must be a string')

    # validate annotations
    f_annotations = f.__annotations__
    if annotations is False:
        annotations = None if f_annotations is None else {**f_annotations}
    elif not is_mapping(annotations):
        raise TypeError('annotations must be None or a mapping')

    # validate global_ns
    sentinel = object()
    if global_ns is None:
        global_ns = f.__globals__
    elif not is_dict(global_ns):
        raise TypeError('function __globals__ must be a dict')
    builtins = global_ns.get('__builtins__', sentinel)
    if builtins is sentinel:
        builtin_ns = {}
    elif is_dict(builtins):
        builtin_ns = builtins
    # the only time __builtins__ can be a module is if it IS builtins
    elif builtins is _builtins:
        builtin_ns = builtins.__dict__
    else:
        raise TypeError('f.__globals__["__builtins__"] must be a dict'
                        f'or the "builtins" module, not {builtins!r}')
    missing = set()
    code        = f.__code__
    co_freevars = code.co_freevars
    co_flags    = code.co_flags
    co_names    = code.co_names
    co_code     = code.co_code

    for co_name in co_names:
        if iskeyword(co_name):
            continue
        ob = global_ns.get(co_name, sentinel)
        if ob is sentinel:
            ob = builtin_ns.get(co_name, sentinel)
            if ob is sentinel:
                if class_was_not_none and co_name == '__class__':
                    continue
                missing.add(co_name)
    module = f.__module__ if module is False else module            
    doc = f.__doc__ if doc is False else module
    if class_was_not_none:
        has_classcell = 'super' in co_names
        # replace LOAD_GLOBAL('__class__') opcodes with LOAD_DEREF('__class__')
        if '__class__' in co_names:
            j = co_names.index('__class__')
            #co_names = co_names[:j] + co_names[j+1:]
            bytecode = bytearray(co_code)
            for instr in dis.Bytecode(code):
                if instr.opname=='LOAD_GLOBAL' and instr.argval=='__class__':
                    has_classcell = True
                    closure = closure or ()
                    i = len(closure)
                    # if len(closure) >= 256,
                    # the LOAD_DEREF opcode will use EXTENDED_ARG
                    if i > 255:
                        repl = b'\x90\x01\x88' + i.to_bytes(3, 'little')
                    else:
                        repl = b'\x88' + i.to_bytes(1, 'little')
                    x = instr.offset
                    bytecode[x:x+2] = repl
            co_code = bytes(bytecode)
        # only add a class cell if necessary
        if has_classcell:
            cell = build_class_cell(cls)
            closure = closure or ()
            # insert/replace the __class__ cell if it is already in freevars
            if '__class__' in co_freevars:
                i = co_freevars.index('__class__')
                j = len(closure) == len(co_freevars)
                closure = (*closure[:i], cell, *closure[i+j:])
            # add if it doesn't
            else:
                co_freevars += ('__class__',)
                closure += (cell,)
    # ensure NOFREE flag is set if there are no frevars
    if not co_freevars:
        co_flags = (co_flags | NOFREE)
        if f.__closure__ is not None:
            raise TypeError('function closure was a tuple when its'
                            'code.co_freevars was empty')
    # since python 3.6, the NOFREE flag actually does what it's
    # supposed to do, so it must be unset to enable access of __closure__
    else:
        co_flags = (co_flags | NOFREE) ^ NOFREE
    code = update_code(
        code,
        freevars=co_freevars,
        flags=co_flags,
        names=co_names,
        code=co_code)
    method = FunctionType(code, global_ns, closure=closure)
    method.__defaults__ = defaults
    method.__kwdefaults__ = kwdefaults
    method.__name__ = name
    method.__qualname__ = qualname
    method.__annotations__ = annotations
    method.__module__ = module
    method.__doc__ = doc
    FunctionType.__dict__['__dict__'].__set__(method, new_dict)
    for wrapper in reversed(wrappers):
        method = wrapper(method)
    return method    

name_getter = attrgetter('__class__.__name__')
@public
class Signature:
        
    def __init__(self, f):
        info  = get_code_info(f)
        flags = get_co_flags(f)
        names = stack = info.varnames
        args, stack = stack[:info.argcount], stack[info.argcount:]
        kwonly, stack = stack[:info.kwonlyargcount], stack[info.kwonlyargcount:]
        kwonly = frozenset(kwonly)
        if flags & VARARGS:
            varargs, *stack = stack
        else:
            varargs = None
        if flags & VARKEYWORDS:
            varkws, *stack = stack
        else:
            varkws = None
        num_positionals = len(args)
        positional_defaults = self.defaults = (f.__defaults__ or ())
        
        num_required_positionals = num_positionals - len(positional_defaults)
        positionals_without_default = args[:num_required_positionals]
        positionals_with_default = args[num_required_positionals:]

        positional_defaults = {k:v for k, v in zip(positionals_with_default,
                                                   positional_defaults)}
        num_kwonlys = len(kwonly)
        kwonly_defaults = f.__kwdefaults__ or {}

        num_required_kwonly = num_kwonlys - len(kwonly_defaults)
        kwonlys_without_default = frozenset(
            kwonly - kwonly_defaults.keys())
        kwonlys_with_default = frozenset(kwonly-kwonlys_without_default)

        self.num_positionals = num_positionals
        self.positionals_without_default = positionals_without_default
        self.positionals_with_default = positionals_with_default
        self.num_kwonlys = num_kwonlys
        self.kwonlys_without_default = kwonlys_without_default
        self.kwonlys_with_default = kwonlys_with_default
    
        d = self.defaults = {**positional_defaults, **kwonly_defaults}
        has_no_default = (frozenset(positionals_without_default)
                          | kwonlys_without_default)
        self.has_no_default = has_no_default
        pwd = positionals_with_default
        pwds = frozenset(pwd)
        pwod = positionals_without_default
        pwods = frozenset(pwod)
        kwd = kwonlys_with_default
        kwod = kwonlys_without_default
        self.accepted = pwds | pwods | kwd | kwod

        def bind(*_args, **_kws):
            length = len(_args)
            vargs = _args[num_positionals:]
            fkws = dict(zip(args, _args))
            update = fkws.update
            kwkeys = _kws.keys()
            kwpop = _kws.pop
            missing_pos = pwod[length:]
            if missing_pos:                
                if not (frozenset(missing_pos).issubset(kwkeys)):
                    error = TypeError(f'{self.name}() missing {len(missing_pos)}'
                                      f' required positional argument: '
                                      f'{", ".join(map(repr, missing_pos))}')
                    raise error
                update(zip(missing_pos, map(kwpop, missing_pos)))
            supplied = kwkeys & pwds
            update(zip(supplied, map(kwpop, supplied)))
            if kwod:
                missing = kwod - kwkeys
                for k in missing:
                    error = TypeError(f'{self.name}() missing {len(missing)}'
                                      f' required keyword-only arguments: '
                                      f'{", ".join(map(repr, missing))}')
                    raise error
                update(zip(kwod, map(kwpop, kwod)))
            supplied = kwkeys & kwd
            update(zip(supplied, map(kwpop, supplied)))
            return fkws, vargs, _kws
        
        self.bind = bind

        self.kwdefaults = f.__kwdefaults__ or {}
        self.info = info
        self.flags = flags
        self.varargs = varargs
        self.args = args
        self.kwonly = kwonly
        self.varkws = varkws
        self.name = f.__name__
        self.annotations = annos = f.__annotations__
        _repr = ()
        for arg in self.args:
            if arg in self.defaults:
                _repr += (f'{arg}={self.defaults[arg]}',)
            else:
                _repr += (arg,)
        #_repr += self.args
        _repr += () if varargs is None else (f'*{varargs}',)
        for arg in self.kwonly:
            if arg in self.defaults:
                _repr += (f'{arg}={self.defaults[arg]}',)
            else:
                _repr += (arg,)
        _repr += () if varkws is None else (f'**{varkws}',)
        self._repr = _repr
        annoreprs = {k:f'{k}: {v.__name__ if isinstance(v, type) else repr(v)}'
                     for k, v in annos.items()}
        annoreprs = {**dict(zip(_repr, _repr)), **annoreprs}
        self._repr_str = ', '.join(map(annoreprs.get, _repr))

        self._repr_str = f'{self.name}({self._repr_str})'
        if 'return' in annos:
            r = annos['return']
            if isinstance(r, type):
                self._repr_str += f' -> {r.__name__}'
            else:
                self._repr_str += f' -> {r}'
    def __repr__(self):
        return f'<{name_getter(self)}: {self._repr_str!r}>'
    
if __name__ == '__main__':
    dupe = lambda ob: ob
    class s(Exception):
        pass
    s = s('faild to raise exception')
    class cls:
        def g(self): return self.__class__
    def f(self): return self.__class__
    cls.f = rebuild_func(f, cls)
    def f(a, b=1, *, c, d=2): pass

    def f2(f):
        x = 'x'
        def i(): return f(x)
        return i
    f2 = f2(f)
    def f3(f):
        x, y = 'x', 'x'
        def i(): return f(x, y)
        return i
    f3 = f3(f)
    closurenone = None
    closure2 = f2.__closure__
    closure3 = f3.__closure__
    r=rebuild_func
    r(f, cls)
    r(f2, cls)
    r(f3, cls)
    r(f, cls, closure_copy=dupe)
    r(f2, cls, closure_copy=dupe)
    r(f3, cls, closure_copy=dupe)


