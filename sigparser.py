
r''' Inspect and log at runtime the calling of Py functions and methods

("Py function" means types.FunctionType by the way)

Functions/classes of note:
    ___________________
    * parse_signature: *************************************************
    *------------------
    *   Internal function that arranges the values in a tuple and dict
    *   into a valid call signature
    *
    *-------------------------------------------------------------------
    _________
    * siggy: **********************************************************
    *--------
    *   Internal class, instances of which implement how the call
    *   signatures are represented when printed
    *
    *-------------------------------------------------------------------
    ______________
    * sigwrapper: ******************************************************
    *-------------
    *   One of the five core functions. When Py functions are wrapped by
    *   `sigwrapper`, each time it is called a message is written to the
    *   output file (defaults to sys.stdout, aka print).
    *
    *   Argument names and default values are extracted directly from
    *   the __code__.co_varnames, __defaults__, __kwonlydefaults__,
    *   function attributes, respectively.
    *
    *-------------------------------------------------------------------
    ___________________
    * show_signatures: *************************************************
    *------------------
    *   Second core function, a class decorator that can quickly wrap
    *   all Py function based methods a class owns and or has access to
    *
    *-------------------------------------------------------------------
    ________________________________________________
    * sigclassmethod, sigstaticmethod, sigproperty: ********************
    *-----------------------------------------------
    *   Final 3 core functions. Because `sigwrapper` is limited in what
    *   it can wrap when used as a decorator from within the class body,
    *   these are required to wrap class methods, static methods, and
    *   properties, respectivley. Their use tells `sigwrapper` that
    *   there will be no unintended side effects of their wrapping after
    *   __init_subclass__, __set_name__, and type.__new__ are called.
    *
    *-------------------------------------------------------------------
    
Other stuff of note:
    ____________________________
    * DEFAULT_FILE = sys.stdout ****************************************
    *---------------------------
    *   Global variable storing the default output file the core
    *   functions will write the signatures to. Changing this to None
    *   will effectively disable the functionality of this module.
    *
    *-------------------------------------------------------------------    
    ________________________
    * MAX_LINE_LENGTH = 160 ********************************************
    *-----------------------
    *   Each function argument is printed on a seperate line. For
    *   example, a module scope function with the signature:
    *   
    *       >>> f(a, b=1, *args, c, d=3, **kws)
    *
    *   when call with the following arguments:
    *   
    *       >>> f(0, c=2)
    *
    *   will write to the specified output file the follwing string:
    *
    *       (
    *       "f(\n"
    *       "    a = <builtins.int object at 0x6D3C4680>,\n"
    *       "    b = 1,\n"
    *       "    c = 2,\n"
    *       "    d = 3,\n"
    *       ")"
    *       )
    *
    *   If MAX_LINE_LENGTH is not None, each of the lines are limited to
    *   at be at most `max(8, MAX_LINE_LENGTH)` characters. The lower
    *   limit is in place to simplify alignment.
    *   
    *   Otherwise when it is None, the entire argument representation
    *   is printed. Note that by default, __repr__ is not automatically
    *   wrapped by any of the functions here due to how easy it is for
    *   __repr__ to cause recursion errors.
    *
    *   The first argument to functions is assumed to be `self`, and
    *   since `self` tends to have huge reprs and is easy to manually
    *   view it, a generic __repr__ similar to object.__repr__ is used
    *   on the first positional argument passed to a function.
    *
    *-------------------------------------------------------------------
'''
import sys
from itertools import filterfalse as _filterfalse
from functools import lru_cache, wraps
from operator import attrgetter as AG, itemgetter as IG, methodcaller as MC
from reprlib import recursive_repr
from types import FunctionType

def _get_chk(tp):
    return type.__dict__['__instancecheck__'].__get__(tp, type)

_is_type = _get_chk(type)
_is_func = _get_chk(FunctionType)
_is_ag = _get_chk(AG)
_is_ig = _get_chk(IG)
_is_mc = _get_chk(MC)

_obattr = object.__getattribute__
_type_mro = type.__dict__['__mro__'].__get__

DEFAULT_FILE = sys.stdout # set me to None if you want me to stfu
MAX_LINE_LENGTH = 160# longest a line can be
IMPLICITLY_CLASS = frozenset('__init_subclass__ __prepare__'.split())
IMPLICITLY_STATIC= frozenset('__new__'.split())
_PTR_SIZE = (sys.maxsize << 1).bit_length() >> 3

class NamedArgs(tuple):

    def __new__(cls, args):
        if args:
            names, vals = [*zip(*args)]
        else:
            names = vals = ()
        self = tuple.__new__(cls, vals)
        self.names = names
        self.repr = args
        self._longest = None
        return self

    @property
    def big_name(self):
        r = self._longest
        if r is None:
            r = self._longest = max(self.names, key=len)
        return r

    def __repr__(self):
        if not self.repr:
            return ''
        lpad = f'%-{len(self.big_name) + 1}s'.__mod__
        (x, y), *rite = self.repr
        left = f'{lpad(x)}= {selfrepr(y)}'

        return ',\n'.join((left, *[f'{lpad(k)}= {v!r}' for k, v in rite]))

class VaArgs(tuple):

    def __repr__(self):
        return f'*{tuple.__repr__(self)}'

class VaKwds(dict):
    def __repr__(self):
        return f'**{dict.__repr__(self)}'

class KwonlyArgs(dict):
    def __repr__(self):
        return ',\n'.join(f'{k} = {v!r}' for k, v in self.items())

def typename(tp):
    return '.'.join(filter(None, (tp.__module__, tp.__name__)))

def selfrepr(obj):
    if _is_type(obj):
        a, b, c = 'class', typename(obj), ''
    else:
        a = typename(type(obj))
        b = 'object at '
        c = f'0x{id(obj):0{_PTR_SIZE*2}X}'
    return f'<{a} {b}{c}>'

class siggy:

    @classmethod
    def from_signature(cls, func, args, kwds=None):
        kwds = {} if kwds is None else kwds
        return cls(func, *parse_signature(func, args, kwds))

    def __init__(self, func, pos, va_args, kwo, va_kwds):
        self.func = func
        self.pos = pos
        self.kwo = kwo
        self.va_args = va_args
        self.va_kwds = va_kwds
        self._repr = None
        self._sig = None

    @property
    def sig(self):
        if self._sig is None:
            self._sig = (NamedArgs(self.pos),
                         VaArgs(self.va_args),
                         KwonlyArgs(self.kwo),
                         VaKwds(self.va_kwds))

        return self._sig

    def __call__(self):
        func = self.func
        pos, va_args, kwo, va_kwds = self.sig
        return func(*pos, *va_args, **kwo, **va_kwds)

    @property
    def func_name(self):
        return getattr(self.func, '__qualname__', None) or self.func.__name__

    @recursive_repr('...')
    def __repr__(self):

        if self._repr is None:
            j = MAX_LINE_LENGTH
            r = '\n'.join(f'    {line}'
                          for lines in map(repr, filter(None, self.sig))
                          for line in lines.split('\n'))
            if j is not None:

                i = (j - 4) if j > 8 else 4
                global sluts
                sluts = r, i, j
                r = '\n'.join((f'{line[:i]} ...' if len(line) > j else line)
                               for line in r.split('\n'))

            self._repr = f'{self.func_name}(\n{r}\n)'

        return self._repr

def parse_signature(func, args, kws):

    code = func.__code__
    names = code.co_varnames
    ac = code.co_argcount
    kc = code.co_kwonlyargcount

    va_names = names[0: ac]
    kw_names = names[ac: ac+kc]

    kwd = func.__kwdefaults__ or {}
    kwo = {}
    for k in kw_names:
        v = kws.pop(k) if k in kws else kwd.get(k, kwo)
        if v is kwo:
            raise TypeError(f"missing required keyword only argument {k!r}")
        kwo[k] = v

    defs = func.__defaults__ or ()
    n_pos = len(va_names)
    n_def = len(defs)
    n_arg = len(args)

    if n_arg < n_pos:
        miss = va_names[n_arg:]
        for k in miss:
            v = kws.pop(k, kwo)
            if v is not kwo:
                args += (v,)
                n_arg += 1
        n_got = n_def + n_arg
        if n_got < n_pos:
            miss = va_names[n_arg:n_pos-n_def]
            for k in miss:
                v = kws.pop(k, kwo)
                if v is kwo:
                    raise TypeError(f'missing required positional argument:'
                                    f'{k!r}')
                args += (v,)
        args += defs
        va_args = ()
    else:
        args, va_args = args[:n_pos], args[n_pos:]

    va_kwds = kws
    return ([*zip(va_names, args)],
            va_args,
            [*kwo.items()],
            va_kwds)

def sigerror(obj):
    m = (f'sigwrapper requires a Python function; got {type(obj).__name__!r}')
    raise TypeError(m)

def _sigwrapper_fromclass(obj, file):
    f = obj.__init__
    if not _is_func(f):
        f = obj.__new__
        if not _is_func(f):
            f = type(obj).__call__
            if not _is_func(f):
                sigerror(obj)
    return sigwrapper(f, file)

def _sigwrapper_fromobj(obj, file):
    f = type(obj).__call__
    if hasattr(obj, '__get__') or not _is_func(f):
        sigerror(obj)
    return sigwrapper(f, file)

def sigwrapper(f, file=None, smartwrap=True):
    '''When `f` is called, prints to `file` the arguments it receieved

    To disable logging set the global variable DEFAULT_FILE to None.

    sigwrapper.w(**kwds) binds the arguments so sigwrapper so it can
    be used with decorator syntax.

    If `smartwrap` is True, will try to detect if it is wrapping one
    of the methods that the interpreter normally silently wraps:
    __prepare__, __init_subclass__, and __new__.

    `f` must be a Python function. It might work if the object is a
    class with a Python function as its __init__ or __new__, or if its
    metaclass.__call__ is a Python function, but I wouldn't count on it.

    classmethod, staticmethod, and property instances will fail here.
    Either wrap them while they're still a function object or use the
    sigclassmethod, sigstaticmethod, and sigproperty wrappers instead.

    The `show_signatures` class decorator does auto-wrap these objects,
    but since `sigwrapper` can be used in the class body scope it has
    no way of knowing for sure that an object is what it claims it is.
    '''

    if not callable(f):
        raise TypeError(f'{type(f).__name__!r} object is not callable')

    if _is_func(f):

        file = sys.stdout if file is None else file

        @wraps(f)
        def wrapper(*args, **kws):
            if DEFAULT_FILE is None:
                return f(*args, **kws)
            s = siggy(f, *parse_signature(f, args, kws))
            print(s, file=file)
            return s()

        if smartwrap:
            name = f.__name__
            if name in IMPLICITLY_STATIC:
                return staticmethod(wrapper)
            if name in IMPLICITLY_CLASS:
                return classmethod(wrapper)

        return wrapper

    if _is_type(f):
        return _sigwrapper_fromclass(f, file)

    return _sigwrapper_fromobj(f, file)
sigwrapper.w = lambda file=None, smartwrap=True: (
    lambda f: sigwrapper(f, file, smartwrap))

def _iterdir(tp, ignore, wrap_inherited):
    yield from ((k, v)
                for cls in (_type_mro(tp) if wrap_inherited else (tp,))
                for (k, v) in cls.__dict__.items() if k not in ignore)

def _wrap_prop_fget(name, cls, fget, file):

    if not callable(fget):
        raise TypeError("property fget is not callable")

    pget = fget
    def fget(self):
        return pget(self)
    fget.__name__ = name
    fget.__qualname__ = f'{cls.__name__}.{name}'
    fget.__module__ = cls.__module__
    t = getattr(cls, name, None)
    if t is not None:
        fget.__doc__ = getattr(t, '__doc__', None)

    def wrapper(self, f=fget):
        if DEFAULT_FILE is None:
            return fget(self)
        s = siggy(f, *parse_signature(f, (self,), {}))
        print(s, file=file)
        return s()
    return wrapper

def show_signatures(cls,
                    wrap_inherited=True,
                    file=DEFAULT_FILE,
                    prop_wraps=frozenset({'fget', 'fset', 'fdel'}),
                    skip_repr=True,
                    skip_new=False,
                    skip_init=False,
                    skip_hash=False,
                    skip_eq=False,
                    ignore=frozenset()):
    '''Apply sigwrapper to all applicable functions belonging to `cls`

    However, the behavior is somewhat different compared to manual
    wrapping with `sigwrapper`. `sigwrapper` may allow classes or other
    instances of user-defined classes to be wrapped, but show_signature
    will never allow it. As mentioned in sigwrapper, this is actually
    able to wrap class and static methods plus properties.

    By default, all three propery fields: fset, fget, and fdel will be
    wrapped automatically.

    Assuming they wrap an appropriate object, class and static method
    instances are replaced with a new instance whose __func__ has been
    wrapped.

    `skip_repr, skip_new, skip_init, skip_hash, and skip_eq`... prevents
    the wrapping of __repr__, __new__, __init__, __hash__, and __eq__,
    respectively. `skip_repr` is True by default, since without special
    care it is pretty much guaranteed to lead to recursion errors.
    The others are by default False, but since they cause problems quite
    often when wrapped, for usability a dedicated toggle is warranted.

    When `wrap_inherited` is True, all objects eligible for wrapping
    inherited from any of its bases are wrapped and explicitly added
    to `cls`, eg:

        class a:
            def f(self):
                return 'a.f'

        class b(a): pass
        b = show_signatures(b)

        >>> 'f' in b.__dict__ and b.__dict__['f'].__wrapped__ is a.f
        True
    '''

    iplus = set()
    if skip_repr:
        iplus.add('__repr__')
    if skip_new:
        iplus.add('__new__')
    if skip_init:
        iplus.add('__init__')
    if skip_hash:
        iplus.add('__hash__')
    if skip_eq:
        iplus.add('__eq__')
    ignore = ignore.union(iplus)

    for name, obj in _iterdir(cls, ignore, wrap_inherited):

        if (not hasattr(obj, '__get__') or _is_type(obj)):
            continue

        if isinstance(obj, (classmethod, staticmethod)):
            repl = type(obj)(sigwrapper(obj.__func__, file, False))

        elif type(obj) is property:
            fget = obj.fget
            fset = obj.fset
            fdel = obj.fdel
            m = "show_signature() can't wrap %s-based property.%s"

            if 'fget' in prop_wraps and fget is not None:
                fget = _wrap_prop_fget(name, cls, fget, file)

            if 'fset' in prop_wraps and fset is not None:
                if not _is_func(fset):
                    raise TypeError(m % (type(fset).__name__, 'fset'))
                fset = sigwrapper(fset, file, False)

            if 'fdel' in prop_wraps and fdel is not None:
                if not _is_func(fdel):
                    raise TypeError(m % (type(fset).__name__, 'fset'))
                fdel = sigwrapper(fdel, file, False)

            repl = property(fget, fset, fdel)

        elif _is_func(obj):
            repl = sigwrapper(obj, file, True)

        else:
            continue

        setattr(cls, name, repl)

    return cls

def sigclassmethod(f, file=DEFAULT_FILE):
    return classmethod(sigwrapper(f, file, False))

def sigstaticmethod(f, file=DEFAULT_FILE):
    return staticmethod(sigwrapper(f, file, False))

class sigproperty(property):

    __slots__ = '_fget', '_fset', '_fdel', '_file'

    def __init__(self, fget=None, fset=None, fdel=None, doc=None, file=None):
        self._fget = self._fset = self._fdel = None
        self.init(fget, fset, fdel, doc, file)

    def init(self, fget=None, fset=None, fdel=None, doc=None, file=None):
        self._fget = fget or self._fget
        self._fset = fset or self._fset
        self._fdel = fdel or self._fdel
        self._file = file
        self.__doc__ = doc or (fget and getattr(fget, '__doc__'))
        return self

    @classmethod
    def _fromproperty(cls, p, file=None):
        return cls(p.fget, p.fset, p.fdel, file)

    def setter(self, f):
        return self.init(fset=f)

    def getter(self, f):
        return self.init(fget=f)

    def deleter(self, f):
        return self.init(fdel=f)

    __doc__ = property.__dict__['__doc__']
    __doc__ = property(__doc__.__get__, __doc__.__set__, __doc__.__delete__)

    def __set_name__(self, cls, name):
        fget = self._fget
        fset = self._fset
        fdel = self._fdel
        file = self._file

        property.__init__(self,
                          sigwrapper(fget, file, False) if fget else None,
                          sigwrapper(fset, file, False) if fset else None,
                          sigwrapper(fdel, file, False) if fdel else None)

if __name__ == '__main__':

    from operator import attrgetter
    cmw = attrgetter('__func__')

    @sigwrapper
    def f(x, y=0, *, a, b='b'):
        pass

    def assert_mw(cls, **attrs):
        'Check if regular methods were wrapped'
        d = cls.__dict__
        for attr, t in attrs.items():
            assert t == hasattr(d[attr], '__wrapped__'), attr

    def assert_csmw(cls, **attrs):
        "Check if class or static methods' __func__ was wrapped"
        d = cls.__dict__
        for attr, t in attrs.items():
            assert t == hasattr(d[attr].__func__, '__wrapped__'), (attr,t)

    def assert_p(cls, prop, fget=0, fset=0, fdel=0):
        "Check if the property descriptor implementors were wrapped"
        p = cls.__dict__[prop]
        assert fget==hasattr(p.fget, '__wrapped__')
        assert fdel==hasattr(p.fdel, '__wrapped__')
        assert fset==hasattr(p.fset, '__wrapped__')

    class meta(type):

        @sigclassmethod
        def __prepare__(cls, name, bases, kwarg=22):
            return {}

        @sigstaticmethod
        def __new__(cls, name, bases, ns, kwarg=22):
            return type.__new__(cls, name, bases, ns)

    assert_csmw(meta, __prepare__=1, __new__=1)

    w = lambda cls: show_signatures(cls, skip_init=0, skip_hash=1, skip_eq=1)
    @w
    class basebase:
        def __init__(self): pass
        def __hash__(self): return -1
        def __eq__(self): return False
        def meth(self): pass

    assert_mw(basebase, __init__=1, __hash__=0, __eq__=0, meth=1)
    class base(metaclass=meta):

        @property
        def x(self):
            'doc of x'
            print('gettin x')
        @x.setter
        def x(self, v):
            print('settin x to', v)
        @x.deleter
        def x(self):
            print('tryina delete x')
    base = show_signatures(base,
                           prop_wraps={'fset'})
    assert_p(base, 'x', fget=0, fset=1, fdel=0)
    assert hasattr(base.x.fset, '__wrapped__')
    assert not hasattr(base.x.fget, '__wrapped__')
    assert not hasattr(base.x.fdel, '__wrapped__')


