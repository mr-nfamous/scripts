
''' Parse call signature of Python functions

`parse_signature` takes a function, a tuple, and a dict and parses which
of the generic *args or **kws is a positional or keyword only argument.

* sigclassmethod
* sigstaticmethod
* sigproperty

^ convenience wrappers for wrapping classmethod/staticmethod/property.
__new__ and __prepare__ *must* be explicitly defined with sigstaticmethod
and sigclassmethod, respectively (__init_subclss__ is also a classmethod).

Change sigparser.DEFAULT_FILE to None to disable printing.
If 80 characters isn't enough, set sigparser.MAX_LINE_LENGTH to a higher
value or None for unlimited line lengths
'''

import sys
from functools import lru_cache, wraps
from types import FunctionType

_is_type = type.__instancecheck__.__get__(type, type)
_is_func = FunctionType.__instancecheck__
_obattr = object.__getattribute__
_type_mro = type.__dict__['__mro__'].__get__

DEFAULT_FILE = sys.stdout # set me to None if you want me to stfu
MAX_LINE_LENGTH = 80 # longest a line can be

IMPLICITLY_CLASS = frozenset('__init_subclass__ __prepare__'.split())
IMPLICITLY_STATIC= frozenset('__new__'.split())

class NamedArgs(tuple):

    def __new__(cls, args):
        if args:
            names, vals = [*zip(*args)]
        else:
            names = vals = ()
        self = tuple.__new__(cls, vals)
        self.repr = args
        return self
    
    def __repr__(self):
        return f', '.join(f'{k}={v!r}' for k,v in self.repr)

class VaArgs(tuple):

    def __repr__(self):
        return f'*{tuple.__repr__(self)}'

class VaKwds(dict):
    def __repr__(self):
        return f'**{dict.__repr__(self)}'
    
class KwonlyArgs(dict):
    def __repr__(self):
        return ', '.join(f'{k}={v!r}' for k, v in self.items())

class siggy:
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

    def __repr__(self):
        if self._repr is None:
            f = self.func_name

            pad = ' '*4
            r = filter(None, map(repr, self.sig))
            r = f',\n'.join(f'{pad}{v}' for v in r)
            r = f'{f}(\n%s\n)' % r

            if MAX_LINE_LENGTH is not None:
                min_size = len(f) + 4
                ix = slice(0, max(MAX_LINE_LENGTH, min_size)-4)
                r = '\n'.join((f'{v[ix]} ...'
                               if len(v) > MAX_LINE_LENGTH
                               else v)
                              for v in r.split('\n'))
            
            self._repr = r
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

    sigwrapper.w(file, smartwrap)(f) can be used to enable decorator
    syntax and passing extra arguments.
    
    If `smartwrap` is True, will try to detect if it is wrapping one
    of the methods that the interpreter normally silently wraps:
    __prepare__, __init_subclass__, and __new__.

    `f` must be a Python function. It might work if the object is a
    class with a Python function __init__ or __new__, or if its
    metaclass.__call__ is a Python function, but I wouldn't count on it.
    
    Since classmethod/staticmethod certainly do not work, there are
    convenience wrappers here (sigclassmethod and sigstaticmethod),
    along with sigproperty which is a property subclass that wraps its
    fget, fset, and fdel functions with `sigwrapper`

    Set the global variable DEFAULT_FILE to None to disable.
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

def _iterdir(tp):
    yield from (item
                for cls in _type_mro(tp)
                for item in cls.__dict__.items())
    
def show_signatures(cls, wrap_inherited=True, file=DEFAULT_FILE):
    '''Apply sigwrapper to all applicable functions belonging to `cls`

    Has somewhat different behavior than manually using sigwrapper.
    
    Since the class is done, it's easier to determine if it's safe to
    wrap something claiming to be a property or classmethod. However,
    *ONLY* python functions and strict subclasses of properties,
    classmethods and staticmethods will work here. Class objects or
    custom descriptor instances are slently ignored.

    If `wrap_inherited` is set, the wrapped class will get a wrapped
    copy of all of methods of its bases that are eligible to display
    signatures.
    '''

    if wrap_inherited:
        iterdir = _iterdir(cls)
    else:
        iterdir = cls.__dict__.items()
        
    for name, obj in iterdir:
            
        if not hasattr(obj, '__get__') or _is_type(obj):
            continue
        
        if isinstance(obj, (classmethod, staticmethod)):
            repl = type(obj)(sigwrapper(obj.__func__, file, False))
        elif type(obj) is property:
            repl = sigproperty._fromproperty(obj, file)
            setattr(cls, name, repl)
            repl.__set_name__(cls, name)
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

    @sigwrapper
    def f(x, y=0, *, a, b='b'):
        pass
    
    class meta(type):
        
        @sigclassmethod
        def __prepare__(cls, name, bases, kwarg=22):
            return {}
        
        @sigstaticmethod
        def __new__(cls, name, bases, ns, kwarg=22):
            return type.__new__(cls, name, bases, ns)

    @show_signatures
    class base(metaclass=meta):

        @property
        def x(self):
            'doc of x'
            print('gettin x')
    

















