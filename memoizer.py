
__all__ = ['memoized']
from functools import partial
from weakref import ref as weakref

class MemoizerType(type):

    __cache__   = {}

    def register(cls, obj, func, /):
        def fin(key):
            del __class__.__cache__[key]
        __class__.__cache__[weakref(obj, fin)] = func
        return obj

    def forget(cls, obj, /):
        key =   weakref(obj)
        try: 
            del cls.__cache__[key]
        except: 
            return key
    
    def __call__(cls, func, /):
        return cls.register(type.__call__(cls), func)

        
class Memoizer(dict, metaclass=MemoizerType):
   
    __slots__ = '__weakref__',
    __hash__  = object.__hash__
    __eq__    = object.__eq__
    __call__  = dict.__getitem__
    
    @property
    def __func__(self, /):
        return self.__class__.__cache__[weakref(self)]
    
    def __missing__(d, k, /):
        return dict.setdefault(d, k, d.__func__(k))
        

def memoized(func, /, *args, **kwds): 
    '''Simple unary function cache wrapper

    If extra arguments are given to this constructor they are
    passed to the given function call as in:
    
        >>> def f(a, b, /, c): 
                return a + b + c

        >>> memoized(f, "y", c="z")('x')
        'xyz'
    
    
    '''
    if func is None:
       
        def memoized_wrapper(f, /, *va, **vk):
            if  not callable(f): 
                raise TypeError('memoized required callable')
            return partial(memoized, f, *args+va, **kwds)(**vk)
        return memoized_wrapper
    
    if (n := len(args) == 1):
        [arg] = args
        if kwds:
            def f(self, key): 
                return self(key, arg, **kwds)
        else:
            def f(self, key):
                return self(key, arg)
    elif n:
        if kwds:
            def f(self, key):
                return w(key, *args, **kwds)
        else:
            def f(self, key):
                return w(key, *args)
    else:
        func = dict.__getitem__
        f = dict.__getitem__

    return Memoizer(f.__get__(func))

