
''' Parse call signature of Python functions

`parse_signature` takes a function, a tuple, and a dict and parses which
of the generic *args or **kws is a positional or keyword only argument.

`sig_shower` 
'''

import sys
from functools import lru_cache, wraps

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

    def __repr__(self):
        if self._repr is None:
            f = getattr(self.func, '__qualname__', self.func.__name__)
            pad = ' '*4
            r = filter(None, map(repr, self.sig))
            r = f',\n'.join(f'{pad}{v}' for v in r)
            r = f'{f}(\n%s\n)' % r
            r = '\n'.join((f'{v[:76]} ...' if len(v) > 80 else v)
                          for v in r.split('\n'))
            self._repr = r
        return self._repr
_is_type = type.__instancecheck__.__get__(type, type)
_is_func = type(lambda:0).__instancecheck__

def parse_signature(func, args, kws):
    global oargs, ofunc, okws
    ofunc, oargs, okws = func, args, kws
    global code, names, ac, kc, va_names, kw_names, kwd, kwo, defs
    global n_pos, n_def, n_arg, va_args, va_kwds
        
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
    global argf, kwof
    argf, kwof = args, kwo
    rargs, rkwds = args, kwo
    return ([*zip(va_names, args)],
            va_args,
            [*kwo.items()],
            va_kwds)


class sigwrapper:
    def __init__(self, f, file=sys.stdout):
        1
        
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
        
    
def sigwrapper(f, file=sys.stdout):
    '''When `f` is called, prints to `file` the arguments it receieved

    `f` must be a Python function. It might work if the object is a
    class with a Python function __init__ or __new__, or if its
    metaclass __call__ is a Python function, but it isn't likely.
    classmethod/staticmethod certainly do not work.
    '''

    if not callable(f):
        raise TypeError(f'{type(f).__name__!r} object is not callable')
        
    if _is_func(f):
        file = sys.stdout if file is None else file
        @wraps(f)
        def wrapper(*args, **kws):
            s = siggy(f, *parse_signature(f, args, kws))
            print(s, file=file)
            return s()
        
        return wrapper

    if _is_type(f):
        return _sigwrapper_fromclass(f, file)

    return _sigwrapper_fromobj(f, file)

def sigclassmethod(f, file=sys.stdout):
    return classmethod(sigwrapper(f, file))

def sigstaticmethod(f, file=sys.stdout):
    return staticmethod(sigwrapper(f, file))

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
                          sigwrapper(fget, file) if fget else None,
                          sigwrapper(fset, file) if fset else None,
                          sigwrapper(fdel, file) if fdel else None)
        

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
    class base(metaclass=meta):
        @sigproperty
        def x(self):
            'lust of x'
            print('gettin x')
    

















