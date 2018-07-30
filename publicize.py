
"""Set of utilities to ease the importing and exporting of modules

    * Detailed error messages make finding name conflicts easy

    * Significantly reduce boilerplate, especially with `star_import`
    and `import_from_object`

    * Simplifies dynamically reloading modules when source code has
    changed but restarting the interpreter is impossible or undesirable

    * NOTE: Whoever calls the functions here (the caller) does not
    matter, only the caller's module. Since referencing objects
    by an identifier only works at the module scope, it would be
    useless to try and have the results of these functions store
    the results in a function's local scope because to access them
    you'd have to do stuff like:
    
        >>> 'star_import('math')
        >>> return vars()['pi']

Functions:
--------------
import_as_copy
--------------
    ** NEW IN 1.5

    Import a shallow copy of a module.

------------------
import_from_object(obj, overwrite=False) -> dict
------------------

    ** NEW IN 1.5
    `Pretends `ob` is a module and imports its public attributes

    This was inspired by random.py. Rather than hand typing out
    every single method, just use this.    

-------
@public(*objects:[str, object], overwrite=False) -> objects[0]:
-------

    Mark objects (or names) as public and automatically append
    them to __all__.

    There are 2 different ways to use it:
        @public(overwrite=False) <- (with or without parentheses)
            Simple decorator for function/class definitions. Adds the
            wrapped object's __name__ attribute to __all__.

        public(object_or_name, *objects_or_names, overwrite=False)
            If an object is passed as an argument, all names that refer
            to that object will be added to __all__. If a string is
            passed, the name will be added, assuming the reference
            actually exists.

----------------
public_constants(**constants) -> constants:
----------------

    Define public global variables, adding their names to __all__.

------------------
public_from_import(module, *names) -> {**imported}:
------------------

    `from module import names` and add the imported names to __all__.

--------------
publish_module(module) -> module:
--------------

    Publish everything that would be gotten with `from module import *`

---------------
reimport_module(module) -> module:
---------------

    Clear a Python module's dict and reimport it.
    
    -> (1.5):

        * It actually works now.
        
----------------
safe_star_import(module) -> {**imported}
----------------

    `from module import *` that will not overwrite existing names

-----------
star_import(module_or_name,
----------- overwrite=False,
            module=False,
            prefix=None,
            ignore_private=False,
            import_metadata=False) -> {**imported}:
            
    Ignore default * import mechanics to import almost everything.

    -> (1.5):
    
        * replaced `ignore_metadata` (which defaulted to True( with
        import_metadata=False

        * Added __getattr__ and __dir__ to the always-ignored list

        * Added a `prefix` argument for automatically mangling imported
        names with a custom identifier prefix. This was initially
        going to be implemented via a new function but there really
        was no reason to do so.

-------------------
reverse_star_import(module, ignore=set())
-------------------

    Remove what would be imported with from module import *
    Objects that have been renamed after being imported are not removed.
    The most useless function ever created.

"""

from __future__ import print_function, with_statement, unicode_literals

__author__ = 'Dan Snider'
__version__ = '1.5.0'

import copy
import functools
import importlib
import os
import runpy
import sys
import __main__
import time

from collections import namedtuple
from types import ModuleType, FunctionType
from operator import attrgetter, itemgetter, methodcaller

PYTHON3 = sys.version_info > (3, 2)
PYTHON2 = not PYTHON3

_STAR_IMPORT_IGNORE = frozenset((
    '__cached__',
    '__doc__',
    '__loader__',
    '__name__',
    '__package__',
    '__spec__',
    '__file__',
    '__builtins__',
    '__all__',
    '__path__',
    '__getattr__', # for 3.7
    '__dir__', # for 3.7
    ))
        
_RIMP_IGNORE = _STAR_IMPORT_IGNORE - frozenset((
    '__doc__',
    '__all__'))

_METADATA = frozenset((
    '__about__',
    '__annotations__',
    '__author__',
    '__authors__',
    '__contact__',
    '__copyright__',
    '__credits__',
    '__date__',
    '__debug__',
    '__deprecated__',
    '__email__',
    '__import__',
    '__license__',
    '__maintainer__',
    '__revision__',
    '__status__',
    '__version__',
    ))
def STR(**kws):
    ns = QF_ATTR(F_LOCALS)
    for ob_name, ob in dict_items(kws):
        if type(ob) is not str:
            raise TypeError("val of '%' wasn't a string constant"%ob_name)
        ns[ob_name] = ob

def typed_consts(tp, **consts):
    ns = QF_ATTR(F_LOCALS)
    tp_name = tp.__name__
    for ob_name, ob in dict_items(consts):
        if type(ob) is not tp:
            er_name = type(ob).__name__
            m = "'%s' should be object of type %s, not '%s'"
            e = TypeError(m % (ob_name, tp_name, er_name))
            raise e
        ns[ob_name] = ob
        
# C macros :)
OB_NAME    = attrgetter('__name__')
F_CO_NAME  = attrgetter('f_code.co_name')
F_CO_CODE  = attrgetter('f_code.co_code')
F_CODE     = attrgetter('f_code')
F_LOCALS   = attrgetter('f_locals')
F_GLOBAL   = attrgetter('f_globals')
F_BACK     = attrgetter('f_back')
D          = attrgetter('__dict__')
DL         = attrgetter('__dict__.__len__')
DI         = attrgetter('__dict__.items')
DK         = attrgetter('__dict__.keys')
GF         = sys._getframe
class_name = attrgetter('__class__.__name__')

def QF_ATTR(func):
    'inline replica for (with `f` as attrgetter) "f(sys._getframe(2))'
    frame = sys._getframe(2)
    return func(frame)

CodeType = (lambda: 1).__code__.__class__

peek = namedtuple('peek', 'named, varargs, varkws, names')
def peek_args(stack_offset=0, ptype=tuple):
    """Get (*posargs, *args, **kws, (*names,) passed to caller

    The simplest explanation is with a demonstration...

        def peek_ns(named, varargs, varkws, names, take_kws=True):
            r = {}
            if named:
                r.update(zip(names, named))
            if take_kws:
                r.update(varkws)
            return r

        def f_parse_args(name):
            p = peek_args()
            ns = peek_ns(*p)
            name(type(ns['x']).__name__)
            return ns

        def f(x, *, y=None, **kws):
            name = ptr()
            return {**f_parse_args(name), 'name':name()}

    >>> print(' && '.join(f'{k}={v!r}' for k, v in f(-22).items()))

    x=-22 && y=None && name='int'

    """

    global fm, pfm
    pfm   = sys._getframe()
    fm    = sys._getframe(2+stack_offset)
    co    = fm.f_code
    ns    = fm.f_locals
    names = co.co_varnames
    flags = co.co_flags

    i = co.co_argcount + get_code_kwonlyargcount(co)
    j = ((4 & flags) or None) and i
    k = ((8 & flags) or None) and ((i+1) if j else i)

    vargs = ns[names[j]] if j is not None else None
    kwargs= ns[names[k]] if k is not None else None
    if not i:
        return peek(ptype(), vargs, kwargs, ())

    x = names[:i]
    return peek(ptype(ns[k] for k in x), vargs, kwargs, x)

def truthfunc(cls):
    'Rename __truth_impl__ to __bool__ if PY3, else __nonzero__'
    get = cls.__dict__.get
    im_func = get('__bool__') or get('__nonzero__') or get('__truth_impl__')
    if not im_func:
        er = ("@truthfunc('%s')\nclass missing truth function" % OB_NAME(cls))
    im_name = OB_NAME(im_func)
    if im_name != '__truth_impl__':
        er = ("@truthfunc('%s')\nclass already has truth function: '%s'"
              % OB_NAME(cls), im_name)
        raise er
    if PYTHON3:
        q = im_func.__qualname__.replace('__truth_impl__', '__bool__')
        im_func.__qualname__ = q
        im_func.__name__ = '__bool__'
        cls.__bool__ = cls.__truth_impl__
    else:
        im_func.__name__ = b'__nonzero__'
        cls.__nonzero__ = cls.__truth_impl__
    del cls.__truth_impl__
    return cls

if PYTHON2:
    from __builtin__ import xrange as range
    from imp import reload as _reload
    from itertools import (ifilterfalse as filterfalse,
                           imap as map,
                           izip as zip,
                           ifilter as filter,
                           groupby)
    def _set_name(ob, name):
        setattr(ob, '__name__', str(name))
    ptr_base = 'class ptr_base(object): __metaclass__ = pmeta'
    mapping_proxy = dict.copy
    get_code_kwonlyargcount = lambda ob: 0
    dict_items = dict.viewitems
    dict_keys = dict.viewkeys
    dict_values = dict.viewvalues

else:
    def set_func_name(f, name):
        f.__name__ = name
    def _set_name(ob, name):
        setattr(ob, '__name__', name)
    ptr_base = 'class ptr_base(metaclass=pmeta): pass'
    from importlib import reload as _reload
    from itertools import filterfalse, groupby
    from types import MappingProxyType as mapping_proxy
    get_code_kwonlyargcount = CodeType.co_kwonlyargcount.__get__
    dict_items = dict.items
    dict_keys = dict.keys
    dict_values = dict.values
    basestring = str

@truthfunc
class NOTHING(object):

    __nothing = None

    def __new__(cls):
        nada = cls.__nothing
        if nada is None:
            nada = cls.__nothing = object.__new__(cls)
        return nada

    def __truth_impl__(self):
        return False
    
    def __repr__(self):
        return 'NOTHING'

NOTHING = NOTHING()
class pmeta(type):

    def __setattr__(self, attr, value):
        raise TypeError("cannot set attribute")

    def __mul__(self, n):

        def ptrs(*args, **kws):
            default = kws.get('default', NOTHING)
            it = iter(args)
            for i in range(max(len(args), n)):
                r = next(it, self)
                yield self(r) if r is not self else self(default)

        return ptrs
exec(ptr_base, globals())

def ptr_safe_base(self, default=None):
    try:
        return self._base
    except:
        return default

def ptr_safe_args(self, arg, n=0, *args):
    if len(args) > n:
        name = sys._getframe(1).f_code.co_name
        raise TypeError("ptr method '%s' expects %d arguments"%(name, n))
    for arg in (arg,)+args:
        if arg is self:
            raise RecursionError("ptr points to self")
    return arg

def ptr_safe_exec(*args, **kws):
    n = len(args)
    if n<2:
        x, y = ((args or 0) and args[0],)*2; n = {x}
    else:
        x, y = range(args); n = set(x, y+1)
    default = kws.pop('default', NOTHING)

    def wrapper(f):
        s = 'argument' if x==y else 'arguments'
        name = f.__name__
        m = "%s() expects %d %s, got %%d"%(name, y-x, s)
        def impl(self, *args):
            if len(args) not in n:
                raise TypeError(m%len(args))
            try:
                base = self._base
            except:
                return default
            t = self._base
            r = f(self, *args)
            if self._base is self:
                raise RecursionError("ptr points to self")
            return r
        return impl
    return wrapper

class ptr(ptr_base):

    __slots__ = ('_base',)

    def __init__(self, ob=NOTHING):
        self._base = ptr_safe_args(self, ob, 0)

    def __call__(self, *args):
        if args:
            self._base = ptr_safe_args(self, args[0], 0, *args[1:])
        return self._base

    @ptr_safe_exec(1)
    def __getattr__(self, a):
        return getattr(self._base, a)

    @ptr_safe_exec(1)
    def __getitem__(self, i):
        if i is Ellipsis:
            return ~self
        return self._base[i]

    @ptr_safe_exec(2)
    def __setitem__(self, k, v):
        self._base[k] = v
        ob = ptr_safe_base(self, NOTHING)
        k, v = ptr_safe_args(self, k), ptr_safe_args(self, v)
        try:
            ob[k]=v
        except:
            return None

    def __len__(self):
        return len(self._base)

    def __invert__(self):
        '''Was a temporary hack when having unicode troubles...

    Leaving in for now
    '''
        def w(ob):
            self(ob)
            return self
        return w
    
    def safe_binop(f):
        import operator
        frame = sys._getframe(1)
        name = "__%s__" % f.strip('_')
        func = getattr(operator, f)
        check = ptr_base.__instancecheck__
        
        def impl(self, other):
            if check(other):
                other = other._base
            return func(self._base, other)
        
        frame.f_locals[name] = impl
        _set_name(impl, name)

    safe_binop('sub')
    def __add__(self, other):
        return self._base + other._base

    def __iter__(self):
        return iter(self._base)

    def __repr__(self):
        name = class_name(self)
        if self._base is self:
            raise RecursionError("%s object refers to self" % name)
        return '%s(%r)'%(name, self._base)

_is_string = basestring.__instancecheck__ # this was very wrong
_is_module = ModuleType.__instancecheck__
_is_list = list.__instancecheck__
_get_frame = sys._getframe
_find_module = sys.modules.get
_SCOPES = {}
_SCOPE_PICKLES = set()

class Scope(object):

    """Scope(module)"""
    __slots__ = ('_module', '_all')
    __getitem__ = property(attrgetter('_module.__dict__.__getitem__'))
    __contains__ = property(attrgetter('_module.__dict__.__contains__'))
    __len__ = property(attrgetter('_module.__dict__.__len__'))
    module_name = property(attrgetter('_module.__name__'))
    get_item = property(attrgetter('_module.__dict__.get'))
    namespace = property(attrgetter('_module.__dict__'))

    @property
    def _modifiable(self):
        return _SCOPES.get(self._module) is self

    @classmethod
    def is_modifiable(cls, module):
        return _SCOPES.get(module) is not None

    def __new__(cls, module, new_object=object.__new__):
        module = validate_module(module)
        name = module.__name__
        if name in _SCOPE_PICKLES:
            raise TypeError('%r is currently pickled'%module.__name__)
        if module in _SCOPES:
            raise TypeError('%r is already being modified'%module.__name__)
        self = new_object(cls)
        self._module = module
        self._all = None
        return self

    def _check_modifiable(method):
        @functools.wraps(method)
        def wrap(self, *args, **kws):
            if _SCOPES.get(self._module) is not self:
                raise TypeError('Scope of %s is read-only.'%self.module_name)
            return method(self, *args, **kws)
        return wrap

    def __enter__(self):
        module = self._module
        name = module.__name__
        if name in _SCOPE_PICKLES:
            raise TypeError('%r is pickled and cannot be modified'%name)
        if module in _SCOPES:
            raise ValueError('%r is already being modified'%self.module_name)
        __all__ = validate_all(self._module)
        if __all__ is not None:
            self._all = __all__
        return _SCOPES.setdefault(self._module, self)

    @_check_modifiable
    def __exit__(self, *args):
        module = self._module
        __all__ = self._all
        if _is_list(__all__):
            module.__all__ = sorted(set(__all__))
        elif __all__ is not None:
            raise ValueError('%r ended up with an invalid __all__ attribute'
                             %self.module_name)
        _SCOPES.pop(module)

    @_check_modifiable
    def __setitem__(self, key, value):
        self._module.__dict__[key] = value

    @_check_modifiable
    def __delitem__(self, key):
        del self._module.__dict__[key]

    @_check_modifiable
    def extend_all(self, elems):
        missing = set(elems) - dict_keys(self._module.__dict__)
        if missing:
            args = ', '.join(map(repr, missing)), self.module_name
            raise NameError('names %s do not exist in %s'%args)
        if self._all is None:
            self._all = []
        self._all.extend(elems)

    @_check_modifiable
    def update_namespace(self, d=(), **kws):
        """module.__dict__.update(d, **kws)"""
        return self._module.__dict__.update(d, **kws)

    def keys(self):
        return dict_keys(self._module.__dict__)

    def values(self):
        unique = []
        append = unique.append
        for elem, group in groupby(dict_values(self.namespace)):
            if elem not in unique:
                append(elem)
        return unique

    @classmethod
    def repair_all(cls, module):
        """Clear invalid entries in module.__all__"""
        pop = module in _SCOPES
        self = _SCOPES[module] if pop else cls(module)
        __all__ = getattr(self._module, '__all__', None)
        if __all__ is not None:
            if not _is_list(__all__):
                if hasattr(__all__, 'index'):
                    __all__ = list(__all__)
            __all__ = list(filter(self.keys().__contains__, __all__))
            self._all = module.__all__ = __all__
        if pop:
            _SCOPES.pop(module, None)

    def public_update(self, d=(), **kws):
        d = dict(d, **kws)
        self.update_namespace(d)
        self.extend_all(d)

    def find_refs(self, item):
        """Find all references to `item` in scope's namespace"""
        for name, value in dict_items(self._module.__dict__):
            if value is item:
                yield name

    def list_imported_names(self, other):
        """Find all names that have been imported from `other`"""
        if isinstance(other, type(self)):
            b = other.namespace
        else:
            b = validate_module(other).__dict__
        a = self._module.__dict__
        imported = dict_keys(a) & dict_keys(b)
        return [k for k in imported if a[k] is b[k]]

    def get_star_imports(self):
        """What's gotten with from module import *"""
        __all__ = validate_all(self._module)
        if __all__ is None:
            return set(iter_public_names(self._module))
        return set(__all__)

    def close(*args):
        if len(args) >= 2:
            module_or_instance = args[1]
        elif len(args) == 1:
            module_or_instance = args[0]
        else:
            raise TypeError('close needs a Scope instance or a module')
        if _is_module(module_or_instance):
            module = validate_module(module_or_instance)
        else:
            module = module_or_instance._module
        self = _SCOPES.get(module)
        if self is not None:
            self.__exit__()

    def __iter__(self):
        return iter(self.keys())

    def __copy__(self):
        raise TypeError('%s cannot be copied'%self.__class__.__name__)

    def __deepcopy__(self, memo):
        raise TypeError('%s cannot be deepcopied'%self.__class__.__name__)

    def __reduce__(self):
        module = self._module
        name = module.__name__
        if _find_module(name) is not module:
            raise ValueError('cannot pickle modules not in sys.modules')
        entered = module in _SCOPES
        instance = _SCOPES.pop(module, self)
        args = (name, self._all, entered)
        _SCOPE_PICKLES.add(name)
        return self._build, args

    @classmethod
    def _build(cls, name, __all__, entered):
        if name not in _SCOPE_PICKLES:
            raise TypeError('%r is no longer pickled'%name)
        module = validate_module(name)
        instance = object.__new__(cls)
        instance._module = module
        _SCOPE_PICKLES.remove(name)
        if entered:
            instance._all = __all__
            self = _SCOPES.setdefault(module, instance)
            if _SCOPES[module] is not self:
                raise TypeError('Scope %r was somehow created even though it '
                                'was already pickled'%name)
            return self
        return instance

    def __repr__(self):
        return '<%s.__all__: %s>'%(self.module_name, self._all)

    _check_modifiable = staticmethod(_check_modifiable)

class InvalidAllError(Exception):
    pass

def validate_all(module):
    """See if a module has a valid __all__ attribute"""
    try:
        __all__ = module.__all__
    except:
        return None
    if hasattr(__all__, 'index'):
        if all(map(_is_string, __all__)):
            import_list = set(__all__)
            if import_list.issubset(dict_keys(module.__dict__)):
                return __all__[:]
            error = InvalidAllError('%s.__all__ contain references to '
                                    'non-existing names')
        else:
            error = InvalidAllError('module %r has an __all__ containing '
                                    'invalid types'%module.__name__)
    else:
        error = InvalidAllError('module %r has an __all__ that is not '
                                'indexable so it cannot be used for star '
                                'imports'%module.__name__)
    raise error
if PYTHON3:  STR(PY_MODULE='PY_MODULE',  EXT_MODULE='EXT_MODULE')
else:       STR(PY_MODULE=b'PY_MODULE',  EXT_MODULE=b"EXT_MODULE")

PY_MODULES = set()

_is_ext_module = lambda m: module_type(m) is EXT_MODULE
_is_py_module = PY_MODULES.__contains__

def get_module2(ob, m_name=None, m_file=None, m_type=None):

    m_name = ptr() if m_name is None else m_name
    m_file = ptr() if m_file is None else m_file
    m_type = ptr() if m_type is None else m_type
    module = None

    if _is_module(m_name(ob)):
        module = sys.modules.get(m_name(ob.__name__))

    if _is_string(m_name()):
        module = sys.modules.get(m_name())
        if module is None:
            try:
                module = importlib.import_module(m_name())
            except:
                module = _get_module_from_filename(m_name())
                m_name(module.__name__)

    if module is None:
        raise TypeError("can't get module from %r"%ob)

    assert m_name() == module.__name__
    if not sys.modules.get(m_name(module.__name__)):
        raise SystemError("coudn't find '%s' in sys.modules"%m_name())
    file = ptr(getattr(module, '__file__', NOTHING)) 
    if file() is NOTHING or clean_fp(m_file[...](file()))==EXT_MODULE:
        m_type(EXT_MODULE)
    else:
        m_type(PY_MODULE)
    return module

LAST_ERROR = []

def _get_last_error():
    'Get the frame when LAST_ERROR in certain circumstances'
    return LAST_ERROR.pop()

def simple_type_check(ob, yh, *r):
    if issubclass(type(ob), yh):
        return ob
    if r:
        t = r[1:]
        if t:
            raise TypeError("simple_type_check(): len(*r) != 1")
        return r[0]
    if LAST_ERROR:
        LAST_ERROR[:] = []
    f = sys._getframe(1)
    LAST_ERROR.append(f)
    n = QF_ATTR(F_CO_NAME)
    g = yh.__name__
    b = type(ob).__name__
    error = TypeError("%s expected a '%s' object; got '%s' instead"%(n,g,b))
    raise error

def clean_fp(file):
    fp = simple_type_check(simple_type_check(file, ptr)(), str).lower()
    if fp.endswith('.pyo') or fp.endswith('.pyc'):
        fp = fp[:-1]
    if fp.endswith('.py'):
        return file(fp)
    elif fp.endswith('.pyd'):
        return EXT_MODULE
    raise ValueError("%r is not a valid python filename"%fp)

def m_load(o, m_name):
    'Get a module from `o` (str, module, or file-like object)'
    assert not isinstance(o, ptr)

    if _is_string(o):
        module = sys.modules.get(o)
        if _is_module(module):
            return simple_type_check(m_name(module.__name__), str) and module
        t = clean_fp(ptr(o))
        valid = {EXT_MODULE, t}.__contains__
        file_b = ptr()
        for name, module in dict_items(sys.modules):
            if not file_b(getattr(module, '__file__', None)):
                continue
            m_file = clean_fp(file_b)
            if valid(m_file) and m_file==t:
                return m_name(name) and module

        o = open(m_name(o), 'rb')

    if not hasattr(o, 'read'):
        raise TypeError('object must be a string or have a read() method')

    name = getattr(o, 'name', NOTHING) or m_name()
    sep = '.' if PYTHON3 else b'.'
    name = os.path.split(name)[1].partition(sep)[0]
    assert isinstance(name, str)
    with o as fp:

        code = compile(fp.read(), name, 'exec')
        module = ModuleType(name)
        exec(code, module.__dict__)

    if hasattr(module, '__file__'):
        del module.__file__

    return m_name(name) and module

def test_m_load():
    import re
    from io import BytesIO as bio

    file = re.__file__
    with open(clean_fp(ptr(file)), 'rb') as fpx:
        src = fpx.read()
        as_fp = bio(src)
    name_as_str = ptr()
    name_as_file = ptr()

    name_as_fp = ptr('re' if PYTHON3 else b're')
    re_from_name = m_load(re.__name__, name_as_str)
    re_from_file = m_load(re.__file__, name_as_file)
    try:
        del sys.modules['re']
        re_from_fp = m_load(as_fp, name_as_fp)
    except Exception as er:
        exc = er
        LAST_ERROR.append(sys._getframe())
    else:
        assert as_fp.closed
        return re, re_from_name, re_from_file, re_from_fp
    finally:
        sys.modules['re'] = re
    raise exc

def _get_module_from_filename(file):
    """Find the module that corresponds to `file`"""

    file = file.lower()
    lowercase = methodcaller('lower')

    for name, module in dict_items(sys.modules):
        module_file = getattr(module, '__file__', NOTHING)
        if module_file is NOTHING:
            continue
        if file == lowercase(module_file):
            return module
    raise ValueError("couldn't load module file: '%s'"%file)

def module_type(module, file=None):
    if file is None:
        file = ptr()
    if not _is_module(module):
        return file(None)

    fp = ptr(file(module)).__file__
    if _is_string(fp):
        if _is_py_module(fp):
            return PY_MODULE

        import linecache
        try:
            linecache.getline(fp, 1)
            PY_MODULES.add(fp)
            return PY_MODULE
        except:
            pass
        name = module.__name__
        raise TypeError("couldn't find source file for %r"%name)
    if fp is None:
        return EXT_MODULE
    raise TypeError("module's __file__ attribute wasn't None or a string")

validate_module = get_module2
is_not_public_name = methodcaller('startswith', '_')

def iter_public_names(ob):
    """Iterate over all public attributes of `ob`"""
    return filterfalse(is_not_public_name, ob.__dict__)

def iter_dunder_names(module):
    """Iterate over all dunder attributes of `module`"""
    for k in validate_module(module).__dict__:
        if k[:2] == '__' and k[-2:] == '__' and len(k) > 3:
            yield k

def iter_private_names(module):
    """Iterate over all private attributes of `module`"""
    for k in validate_module(module).__dict__:
        if k and k[0] == '_':
            if len(k) < 4 or (not (k[-2:] == '__' and k[:2] == '__')):
                yield k

def true_star_imports(ob, ignore_private, ignore_list, import_metadata):
    '''Calculate everything that should be imported with *import'''
    ig = set(ignore_list) | _STAR_IMPORT_IGNORE
    if not import_metadata:
        ig |= _METADATA
    if ignore_private:
        pub = set(iter_public_names(ob))
    else:
        pub = dict_keys(D(ob))
    return frozenset(pub - ig)

def get_full_name(obj):
    name = getattr(obj, '__qualname__', obj.__name__)
    if hasattr(obj, '__module__'):
        return '%s.%s'%(obj.__module__, name)
    return name

def hex_id(obj, nibs=((sys.maxsize.bit_length()+7)//8) * 2):
    return '0x{:0{nibs}X}'.format(id(obj), nibs=nibs)

def generic_repr(obj):
    ob_type = type(ob)
    objtype = 'class' if type(obj) is type else OB_NAME(ob_type)
    try:
        return '<%s %s at %s>' % (objtype, get_full_name(obj), hex_id(obj))
    except:
        return safe_repr(obj)

def safe_repr(obj, maxlen=50):
    obj_repr = repr(obj)
    if len(obj_repr) < maxlen:
        return obj_repr
    obj_repr = obj_repr[:maxlen]
    return '<%s object %s at %s>'%(type(obj).__name__, obj_repr, hex_id(obj))

def _get_calling_module(depth=0, *args, **kws):
    """Get the module that invoked a function"""
    return _find_module(_get_frame(2+depth).f_globals.get('__name__'))

def _validate_kws(kws):
    for kw in kws:
        args = (kw, _get_frame(1).f_code.co_name)
        error = TypeError('%r is not a valid kw argument for function %r'%args)
        raise error

def _public(module, *objects, **kws):
    overwrite = kws.pop('overwrite', False)
    _validate_kws(kws)
    validated = {}
    update = validated.update
    with Scope(module) as context:
        for ob in objects:
            if _is_string(ob):
                update(_validate_public_alias(ob, context))
            else:
                update(_validate_public_object(ob, context,  overwrite))
        context.public_update(validated)
    return objects[0]

def _validate_public_alias(ob, context):
    if ob in context.keys():
        return {ob: context.namespace[ob]}
    else:
        raise NameError('module %r has no attribute %r to publish'
                        %(context.module_name, ob))

def _validate_public_object(ob, context, overwrite):
    refs = [k for k, v in dict_items(context.namespace) if v is ob]
    if not refs:
        ob_name = getattr(ob, '__name__', NOTHING)
        if ob_name is NOTHING:
            ob_name = None
        if _is_string(ob_name):
            val = context.get_item(ob_name, ob)
            if (val is ob) or overwrite:
                return {ob_name: val}
            else:
                args = context.module_name, ob_name, generic_repr(val)
                raise ValueError("'%s.%s' is already public as %s"%args)
        else:
            raise NameError('in module %r there is no name for %s'
                             %(context.module_name, safe_repr(ob)))
    return dict.fromkeys(refs, ob)

def public(*objs, **kws):
    """Register objects to __all__ automatically

    Unless `overwrite` is True, two distinct objects with the same name
    will raise an error, otherwise the latter will replace the former.
    """
    module = _get_calling_module()
    if not objs:
        return lambda *objects: _public(module, *objects, **kws)
    return _public(module, *objs, **kws)

public(public)

def public_alias(*args):
    """Deprecated"""
    return public(*args)

@public
def public_constants(**constants):
    """Define public global variables and return them in a new dict"""
    with Scope(_get_calling_module()) as context:
        for k in dict_keys(constants) & context.keys():
            if context[k] is not constants[k]:
                args = context.module_name, k, generic_repr(context[k])
                raise ValueError("'%s.%s' is already public as %s"%args)
        context.public_update(constants)
    return constants

@public
def safe_star_import(module):
    """Make sure a normal star import doesn't overwrite anything"""
    module = validate_module(module)
    caller = _get_calling_module()
    with Scope(caller) as context, Scope(module) as imported_context:
        import_list = imported_context.get_star_imports()
        for name in context.keys() & import_list:
            args = context.module_name, name, generic_repr(context[name])
            raise NameError('%s.%s already exists as %s'%args)
        imported = {k: imported_context[k] for k in import_list}
        context.namespace.update(imported)
    return imported

@public
def star_import(mod_or_name, **kws):
    """Ignores default * import mechanics to import almost everything

    If a `prefix` is provided, it will be prepended to the imported
    names.
    
    If `ignore_private` is set to True, _sunder (private) names will
    not be imported.

    Items in `ignore_list` will not be imported.

    If `import_metadata` is True, even module metadata is imported.
    
    Names that already exist in the calling module's namespace will
    be overwritten if `overwrite` is set to True, otherwise an error
    will be raised.

    If `module` is True, returns module instead of dict.
    
    Certain dunder names required by the import machinery are never
    imported. These include __name__, __file__, and __loader__,
    among others (see publicize._STAR_IMPORT_IGNORE for a full list).

    When provided, a prefix can greatly simplify the common idiom:

        >>> from math import pi as _pi, cos as _cos
        # to
        >>> star_import('math', prefix='_')

    Furthermore, the usual method of keeping the information about
    where a function comes from (importing the entire module)
    incurs a signficant performance cost due to the required
    __getattribute__ call on every lookup.

    If instead the module name is used as a prefix, this information
    is kept and the performance cost is eliminated.

        >>> # slow method
        >>> import math
        >>> print(math.ceil(math.pi * math.e))
        9
        >>> # fast method
        >>> star_import('math', prefix='math_')
        >>> print(math_ceil(math_pi * math_e))
        9

    """
    
    module = validate_module(mod_or_name)

    imp_meta  = kws.pop('import_metadata', False)
    ig_priv   = kws.pop('ignore_private', False)
    ig_list   = kws.pop('ignore_list', False) or set()
    overwrite = kws.pop('overwrite', False)
    r_module  = kws.pop('module', False)
    prefix    = kws.pop('prefix', '')
    _validate_kws(kws)
    
    import_list = true_star_imports(module, ig_priv, ig_list, imp_meta)
    rename_list = {}
    for name in import_list:
        if not prefix:
            rename_list[name] = name
            continue
        pname = '%s%s'%(prefix, name)
        if pname in _STAR_IMPORT_IGNORE:
            args = name, prefix, pname
            m = ("imported name '%s' using the prefix '%s' will '"
                 "overwrite the special module name: '%s'") % args
            raise TypeError(m)
        rename_list[name] = pname
        
    caller = _get_calling_module()
    with Scope(caller) as context, Scope(module) as imported_context:

        imported = {k:imported_context[k] for k in import_list}
        
        if not overwrite:
            for name in import_list & context.keys():
                old, new = context[name], imported_context[name]
                if old is new:
                    continue
                current_ob = generic_repr(context[name])
                imported_ob = generic_repr(imported_context[name])
                module_name = context.module_name
                imported_name = imported_context.module_name
                args = imported_name, name, imported_ob, name, current_ob
                error = ImportError('tried importing %s.%s as %s but '
                                    '%r already exists as %s'
                                    %args)
                raise error
            else:
                import_list -= context.keys()
                
        imported = {v:imported[k] for k, v in dict_items(rename_list)}
        context.namespace.update(imported)
    return module if r_module else imported

@public
def public_from_import(module_or_name, *names, **kws):
    """publish the results of `from mod_or_name import name`

    If `module` is True, returns the module, otherwise returns a
    dict containing the imported items.

    If `overwrite` is True, allow the import to replace any names that
    already exist instead of raising an error.

    """
    overwrite = kws.pop('overwrite', False)
    r_module = kws.pop('module', False)
    _validate_kws(kws)
    module = validate_module(module_or_name)
    caller = _get_calling_module()
    with Scope(caller) as context, Scope(module) as imported_context:
        import_list = set(names)
        for name in import_list - imported_context.keys():
            args = module.__name__, name
            raise ImportError('module %r has no attribute %r'%args)
        imported = {k:imported_context[k] for k in import_list}
        if not overwrite:
            for name, value in dict_items(imported):
                if context.get_item(name, value) is not value:
                    args = context.module_name, name, generic_repr(ns[name])
                    raise ValueError("'%s.%s' is already public as %s"%args)
        context.public_update(imported)
    return imported if not r_module else module

@public
def publish_module(module, **kws):
    """Publish everything you would get with `from module import *`

    If `overwrite` is True, allow the import to replace any names that
    already exist instead of raising an error.
    """
    overwrite = kws.pop('overwrite', False)
    _validate_kws(kws)
    caller = _get_calling_module()
    module = validate_module(module)
    with Scope(caller) as context, Scope(module) as imported_context:
        import_list = imported_context.get_star_imports()
        if not overwrite:
            for name in context.keys() & import_list:
                if context[name] is imported_context[name]:
                    continue
                raise ImportError('%r already exists'%name)
        context.public_update({k: imported_context[k] for k in import_list})
    return module

@public
def reverse_star_import(module_or_name, ignore=None):
    """Remove what would be imported with from module import *"""
    module = validate_module(module_or_name)
    caller = _get_calling_module()
    try:
        ignore = set() if ignore is None else set(ignore)
    except TypeError:
        raise TypeError('ignore must be a list of names not to be deleted')
    with Scope(caller) as context, Scope(module) as imported_context:
        for name in ignore - context.keys():
            error = NameError('%r has no attribute %r to keep from being '
                              'deleted'%(context.module_name, name))
            raise error
        for name in imported_context.get_star_imports() - ignore:
            if context[name] is imported_context[name]:
                del context[name]

@public
def reimport_module(ob, local=True):
    """Rebuild a module from its source

    If `local` is False, all other modules will be affected unless they
    pre-imported things. Otherwise, no changes are made to sys.modules
    and a brand new module whose namespace has been freshly repopulated
    with brand new objects is returned. The module attributes necessary
    to run the import system are always recycled.

    NOTE: Extension modules cannot be reloaded. The most this can do
    for extension modules is build a new module object for local use,
    but since objects owned by extension modules are statically
    allocated any changes made directly to the objects will be reflected
    globally.
    """
    
    if 1:
        m_name, m_type, m_name, m_file = (ptr*4)()
        module = get_module2(ob, m_name, m_file, m_type)
        result = ModuleType(m_name())
        m_dict, r_dict = D(module), D(result)

    if m_type() == EXT_MODULE:
        if not local:
            return module
        r_dict.update(m_dict)
        return result

    for k in (dict_keys(r_dict) & dict_keys(m_dict)):
        r_dict[k] = m_dict[k]

    t_dict = r_dict.copy()
    with open(m_file()) as fp:
        r_code = compile(fp.read(), m_file(), 'exec')
        exec(r_code, t_dict)

    result.__file__ = m_file()
    t_dict.update(r_dict)
    d = {k: t_dict[k] for k in (dict_keys(t_dict) - dict_keys(r_dict))}
    r_dict.update(d)

    if not local:
        result.__cached__ = module.__cached__
        m_dict.clear()
        m_dict.update(r_dict)
        result = module
        
    return result

PROFILES = {}

@public
def profile():
    caller = _get_calling_module()
    if caller in PROFILES:
        profile_end = PROFILES.pop(caller)
        return profile_end()
    t = time.time()
    def profile_end():
        print('published %s in %.03f seconds'%(caller.__name__,time.time() - t))
    PROFILES[caller] = profile_end

@public
def import_as_copy(module_or_name, **kws):
    """Import a shallow copy of a module

    The module object itself can be modified without global effects,
    but it will have the same contents as the global version, so
    modifiying any mutable objects it owns will be relfected throughout
    the global namespace.

    Almost as useless as reverse_star_import
    """

    overwrite = kws.pop('overwrite', False)
    _validate_kws(kws)

    m_name, m_file, m_type = (ptr*3)()
    module = get_module2(module_or_name, m_name, m_file, m_type)
    result = ModuleType(m_name())
    D(result).update(D(module))
    
    with Scope(_get_calling_module()) as context:
        if m_name() in context and not overwrite:
            x, y = context.module_name, m_name()
            raise NameError('module %s already exists in %s'%(y, x))
        context[m_name()] = result
        
    return result

@public
def import_from_object(ob, overwrite=False):
    """Pretends `ob` is a module and imports its public attributes

    Returns all of the "imports" in a new dict.
    """
    cls = type(ob)
    if issubclass(cls, ModuleType):
        raise TypeError("module object has no methods")
    with Scope(_get_calling_module()) as context:
        ns = dict(cls.__dict__) # dict cast cause of MappingProxyType
        p = set(iter_public_names(cls))
        if not overwrite:
            for k in p & context.keys():
                raise ValueError("%r is already already exists"%k)
        imported = {k:getattr(ob, k) for k in p}
        context.public_update(**imported)
    return imported

