# I needed a way to use two tuples as dict keys when either object
# could be unhashable. Completely unecessary but too beautiful to
# destroy so here it'll stay until github erases it.

from functools import lru_cache
from itertools import repeat
from operator import itemgetter as IG

class Pear:

    __slots__ = '__call__', '__eq__', '__getitem__', '__hash__', '__lt__'
    
    cash    = lru_cache(4096)
    primary = property(IG(0))
    backup  = property(IG(1))

    @staticmethod
    def hashfunc(obj, bhash=cash(hash), ohash=object.__hash__):
        try:
            r = bhash(obj)
        except:
            r = ohash(obj)
        return 12345678 if h == -1 else h
        
    def __repr__(self, two=slice(2)):
        return f'{type(self).__name__}{self[two]}'

    def __new__(hash=hashfunc.__func__):

        def __new__(cls, a, b, hash, f):

            x = object.__new__(cls)
            c = a, b
            h = hash(a)

            if h == -1:
                h = 12345678

            def __eq__(y, a=a, b=b, c=c):
                return ( ( (x is y   )                           ) or
                         ( (a == y[0])  and (b == y[1])) if f(y) else
                         ( (a == y   )  or  (b == y))            )

            x.__hash__    = repeat(h).__next__
            x.__call__    = repeat(c).__next__
            x.__eq__      = __eq__
            x.__getitem__ = c.__getitem__

            try:
                assert not (c < c)

                def __lt__(y, a=a, b=b, c=c):
                    return (
                        ( (x is not y   )                        ) and
                        ( (a      < y[0]) or (a < y[1]) ) if f(y) else
                        ( (a      < y   ) or (b < y   ) )        )

                x.__lt__ = __lt__

            except:
                x.__lt__ = object.__lt__.__get__(x)

            return x

        @staticmethod
        def __tmp__(cls, a, b, hash=hash, f=0):
            f = __new__
            c = __class__
            f.__defaults__ = hash, c.__instancecheck__
            c.__new__ = staticmethod(f)
            return c(a, b)
        return __tmp__

    __new__ = __new__()
