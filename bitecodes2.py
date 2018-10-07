
import ast
import builtins
import copy
import dis
import opcode
import re
import sys

from collections import deque, OrderedDict as odict
from functools import lru_cache, partial as PT
from operator import *
from types import *
from operator import attrgetter as AG, itemgetter as IG
from sys import _getframe as GF

NULL = 0.0
DUMMY_GLOBALS = {'__builtins__':__import__('builtins')}
DUMMY_CODE    = compile('pass', '', 'single')
assert ((lambda a, b=f'{DUMMY_GLOBALS}': b == f'{DUMMY_GLOBALS}')
        (eval(DUMMY_CODE, DUMMY_GLOBALS)))

co_code_slots = (
        "co_argcount",  "co_kwonlyargcount", "co_nlocals",
        "co_stacksize", "co_flags",          "co_code",
        "co_consts",    "co_names",          "co_varnames",
        "co_filename",  "co_name",           "co_firstlineno",
        "co_lnotab",    "co_freevars",       "co_cellvars")
CODE_SLOTS = attrgetter(*co_code_slots)

split = str.split
func_mdata = split("__dict__ __doc__ __module__ __name__ __qualname__")
func_rdata = split("__globals__ __closure__")
func_wdata = split("__annotations__ __code__ __defaults__ __kwdefaults__")
func_write = *sorted((*func_mdata, *func_wdata)),
func_slots = *sorted((*func_write, *func_rdata)),

FUNC_MDATA = AG(*func_mdata)
FUNC_RDATA = AG(*func_rdata)
FUNC_WDATA = AG(*func_wdata)
FUNC_WRITE = AG(*func_write)
FUNC_SLOTS = AG(*func_slots)

dict_values_check =  type({}.values()).__instancecheck__

code_check   =  CodeType.__instancecheck__
deque_init   =  deque.__init__
frame_check  =  FrameType.__instancecheck__
func_check   =  FunctionType.__instancecheck__
module_check =  ModuleType.__instancecheck__
new_deque    =  deque.__new__
str_check    =  str.__instancecheck__
type_check   =  type.__instancecheck__.__get__(type,type)
type_flags   =  type.__dict__['__flags__'].__get__

ali_pat = re.compile(r'(?xi:([a-z0-9_]+) [ ]*?'
                     r'([=+!~@%^&*-]+)   [ ]*?'
                     r'([^\n]+))')

attrpattr = re.compile(b'(?P<y>\x6a[\x00-\xff])|(?P<n>[^\x6a][\x00-\xff])')
set_check = set.__instancecheck__

_func_lookers = {k:FunctionType.__dict__[k].__get__ for k in func_slots}
_func_lookerx = [FunctionType.__dict__[k].__get__ for k in func_slots]

def ass_ali(src, sortkey=IG(0), prog=ali_pat.findall):
    'Align source code assignment operations; without sortkey no sorting occurs'
    src = src.strip()
    abc = prog(src)
    if sort:
        abc.sort(key=IG(0))
    t,*x= zip(*abc,)
    pad = len(max(t, key=len))
    txt = '\n'.join(f'{a:<{pad}} {b} {c}' for a,b,c in abc)
    return txt

def heap_check(cls, tc=type_check, tf=type_flags):
    return tc(cls) and tf(cls)&512

def init_func(func,  __annotations__, __code__, __defaults__, __kwdefaults__,
              __dict__,  __doc__,   __module__, __name__, __qualname__):

    func.__annotations__ = __annotations__
    func.__code__        = __code__
    func.__defaults__    = __defaults__
    func.__kwdefaults__  = __kwdefaults__

    func.__dict__        = __dict__
    func.__doc__         = __doc__
    func.__module__      = __module__
    func.__name__        = __name__
    func.__qualname__    = __qualname__
    return func

def func_init_fast(func, __annotations__,  __dict__, __doc__,  __kwdefaults__,
                   __module__, __qualname__):

    func.__annotations__ = __annotations__
    func.__kwdefaults__  = __kwdefaults__

    func.__dict__     = __dict__
    func.__doc__      = __doc__
    func.__module__   = __module__
    func.__qualname__ = __qualname__
    return func

def copy_func(func, **copiers):
    g = copiers.get
    f = {k: _func_lookers[k](func) for k in func_slots}
    c = {k: (copiers[k](f[k]) if k in copiers else f[k]) for k in func_slots}
    p = c.pop
    f = FunctionType(p('__code__'),
                     p('__globals__'),
                     p('__name__'),
                     p('__defaults__'),
                     p('__closure__'),
                     )
    return func_init_fast(f, **c)

class CodeTraverser(deque):
    '''Find all code objects associated with something

    Will traverse (a select few) iterables and type objects in search
    of other objects - specifially, functions or objects with a __code__
    attribute or a __func__ attribute that itself has a __code__
    attribute - which it can use to find code objects, only to turn
    around and traverse *those* code objects' co_const fields for even
    more code objects (probably)!

    Try and wrap your head around that nonsense.

    While this is a deque subclass, the "limit" parameter doesn't work
    like deque.maxlen. Instead of exhausting the iterable ending up with
    the last `maxlen` items in the sequence it stops searching as soon
    as it has found `limit` code objects or when it can't find anymore.

    This should easily be able to be refactored into a more generic
    recursive Python object visitor.
    '''

    __slots__ = 'lists', 'limit', 'start'

    def __init__(self, ob, limit=200):

        if hasattr(ob, '__iter__'):

            if not isinstance(ob, (list, tuple, set, dict_values)):
                m = ('an iterable argument must be a list, set, tuple, '
                     f'or dict_values object, not {type(obj).__name__!r}')
                raise TypeError(m)

            temp = deque(filter(None, ob), limit)
        elif ob:
            temp = deque([ob], limit)
        else:
            raise TypeError(f"can't traverse {type(ob).__name__!r} object")

        self.limit = limit
        self.lists = new_deque(__class__)
        self.extend(temp)
        temp = [*self.__iter_internal()]
        self.clear()
        self.lists.clear()
        self.extend(temp)

    def __repr__(self):
        t = type(self.start).__name__
        return f'<codetraverser (started with {t!r}): {len(self)} code objects>'

    def add_list(self, it):
        self.lists.append(deque(it))

    def next_item(self):
        pop = self.popleft
        lim = self.limit
        while lim > 0:
            if self:
                ob = pop()
                if ob is not None:
                    return ob
            elif self.lists:
                self.extend(self.lists.popleft())
            else:
                self.limit = -1
                return None

    def next_code_object(self):

        get_next_ob = self.next_item

        while self.limit > 0:

            ob = get_next_ob()
            if ob is None:
                raise StopIteration

            co = maybe_code(ob)
            if not co:
                if heap_check(ob) or module_check(ob):
                    self.add_list(filter(callable, ob.__dict__.values()))
                continue

            self.add_list(co.co_consts)
            self.limit -= 1
            return co

    def __iter_internal(self):
        if self.limit < 0:
            raise TypeError("already initialized")
        f = self.next_code_object
        while 1:
            item = f()
            if item is None:
                if self.limit > 0 and (self or self.lists):
                    raise TypeError("a none slipped through somehow before "
                                    "the other elements had been traversed")
                return
            yield item

    def __iter__(self, f=deque.__iter__):
        if self.limit < 0:
            return f(self)
        return self.__internal_iter()

def maybe_code(ob, mode=None, filename='',):
    if func_check(ob):
        ob = ob.__code__
    elif not code_check(ob):
        if mode is not None and str_check(ob):
            try:
                ob = compile(ob, filename, mode)
            except:
                return None
        else:
            ob = look4code(look4func(ob))
    return ob

def _test(x:int, y=0):
    def wrapper(cls):
        cls.hng = str
        return cls
    @wrapper
    class cls:
        def a(self): pass
        @staticmethod
        def b(): return [i for i in x]
        @classmethod
        def c(): return 'moist'

    return Lass

def codewalker(root, max_objs=256):
    'Recursively locate (up to `max_objs`) code objects associated with`root`'
    head, tail, code = deque(), deque(), maybe_code(root, 'exec')

    if code:
        head.append(code)
    elif (heap_check(root) or module_check(root)):
        head.extend(root.__dict__.values())
    else:
        raise TypeError(f'{type(root).__name__} not a valid start object')

    pop_head, push_head = head.pop, head.extend
    pop_tail, push_tail = tail.popleft, tail.append

    while max_objs > 0:

        while not head:
            if not tail:
                return
            push_head(filter(None, pop_tail()))

        ob = pop_head()
        co = maybe_code(ob)

        if co:
            push_tail(co.co_consts)
            max_objs -= 1
            yield co
        elif heap_check(ob) or module_check(ob):
            push_tail(ob.__dict__.values())

def attrchecker_func(ob):
    try:
        return ob.attr
    except:
        return None

attrchecker_code = attrchecker_func.__code__

def repl_co_names(_7,c,_0,_1,_2,_3,_4,_5,_6,_8,_9,_a,_b,_c,_d,_e):
    return c(_0, _1,_2,_3,_4,_5,_6,_7,_8,_9,_a,_b,_c,_d,_e)

def _repl_temp(_0,_1,_2,_3,_4,_5,_6,_7,_8,_9,_a,_b,_c,_d,_e, c):
   return c(_0, _1,_2,_3,_4,_5,_6,_7,_8,_9,_a,_b,_c,_d,_e)

def co_easy_repl(**slots):
    replacer

defgetter = AG(*[co_code_slots[i] for i in filter((7).__ne__, range(15))])
repl_co_names.__defaults__ = (CodeType, *defgetter(attrchecker_code))

class attrchecker:
    global attrcheck

def attrchecker(attr, dummy={'__bultins__':None}):
    return FunctionType(repl_co_names((attr,)), dummy)

class codereplacer:

    __slots__ = ('co_argcount', 'co_kwonlyargcount', 'co_nlocals',
                 'co_stacksize', 'co_flags', 'co_code', 'co_consts',
                 'co_names', 'co_varnames', 'co_filename', 'co_name',
                 'co_firstlineno', 'co_lnotab', 'co_freevars',
                 'co_cellvars')

    def replace(self,
                co_argcount=NULL,  co_kwonlyargcount=NULL, co_nlocals=NULL,
                co_stacksize=NULL, co_flags=NULL,          co_code=NULL,
                co_consts=NULL,    co_names=NULL,          co_varnames=NULL,
                co_filename=NULL,  co_name=NULL,           co_firstlineno=NULL,
                co_lnotab=NULL,    co_freevars=NULL,       co_cellvars=NULL):
        params = {**vars()}
        return self._replace(params.pop('self').__code__, **params)

    def __new__(cls,               __code__,
                co_argcount=NULL,  co_kwonlyargcount=NULL, co_nlocals=NULL,
                co_stacksize=NULL, co_flags=NULL,          co_code=NULL,
                co_consts=NULL,    co_names=NULL,          co_varnames=NULL,
                co_filename=NULL,  co_name=NULL,           co_firstlineno=NULL,
                co_lnotab=NULL,    co_freevars=NULL,       co_cellvars=NULL):
        params = {**vars()}
        self = object.__new__(params.pop('cls'))
        return self._replace(params.pop('__code__'), **params)

    def _replace(self, code=NULL, *, slots=__slots__, **replacements):

        if code is NULL:
            code = self.__code__

        fields = []
        for slot in slots:
            value = replacements.pop(slot)
            if value is NULL:
                value = getattr(self, slot, self)
                if value is self:
                    value = getattr(code, slot)
            fields.append(value)
            setattr(self, slot, value)

        self.__code__ = CodeType(*fields)
        return self

    def __call__(self, globals, name=None, argdefs=(), kwdefs=None, closure=()):
        f = FunctionType(self.__code__,
                         globals,
                         self.co_name if name is None else name,
                         argdefs if argdefs else None,
                         closure if closure else None)
        if kwdefs:
            f.__kwdefaults__ = kwdefs
        return f

    _as_tuple = property(AG(*__slots__))
    __slots__ +=  ('__code__',)

look4func = attrchecker('__func__')
look4code = attrchecker('__code__')

template1 = r'''if 1:
    def {name}({signature}):
{src}
'''

def compile_func(f_globals, name, src, vnames, argcount,  kwcount, co_flags=0,
                 f_locals=None, f_closure=None, defaults=(), kwdefaults=None,
                 filename=None):
    dmap = {}
    free = len(vnames)
    va_args = truth(co_flags & 4)
    va_kwds = truth(co_flags & 8)

    need = (argcount + kwcount + va_args + va_kwds)

    if free != need:
        if free < need:
            m = 'not enough parameter names; got {1} when {0} are required'
        elif free > need:
            m = 'too many parameter names; need exactly {0} but got {1}'
        raise TypeError(m.format(need, free))

    sig = []
    if need:
        names = [*vnames]

        if argcount:
            x = names[:argcount]
            if defaults:
                dmap.update(zip(x[-len(defaults):], defaults))
            sig.extend(x)
            names = names[argcount:]

        if va_args:
            sig.append(f'*{names.pop(0)}')
            if kwcount:
                x, names = sig.extend(names[:kwcount]), names[kwcount:]

        elif kwcount:
            sig.append('*')
            x, names = sig.extend(names[:kwcount]), names[kwcount:]

        if va_kwds:
            sig.append(f'**{names[0]}')

    signature = ', '.join(sig)
    src = '\n'.join(f'{" "*8}{line}' for line in src.strip().split('\n'))
    src = template1.format_map(vars())

    if filename is None:
        filename = '<string>'

    if f_locals is None:
        f_locals = {}

    if '__builtins__' not in f_globals:
        f_globals['__builtins__'] = builtins

    code = compile(src, filename, 'exec')
    eval(code, f_globals, f_locals)
    func = f_locals[name]
    if defaults:
        func.__defaults__ = defaults
    if kwdefaults:
        func.__kwdefaults__ = kwdefaults
    return func

