
''' NULL for when None isn't enough (aka always...)

Note the __bool__ "method" speed hack. I have no clue as to why Python
discards `self` for non-descriptor callables used as dunders, but it
does.

'''

__all__ = ['new_singleton_type', 'NULL']

from itertools import repeat
from sys import _getframe as GF

from typestuff import type_base, type_dict, type_name, type_module

class SingleSelf:

    def __get__(self, obj, cls):
        return self.__self__

class SingletonType(type):

    def __call__(self):
        return self.__self__

    def __repr__(self):
        m = type_module(self)
        n = type_name(self)
        return f"<class '{m}.{n}'>"

    @classmethod
    def _make(cls, name, is_true=False, *slots, prepare=dict, **kws):
        ns = prepare(__slots__=slots,
                     __bool__=repeat(is_true).__next__,
                     )
        return type.__new__(cls, name, (SingletonBase,), ns)

class SingletonBase:

    __self__ = SingleSelf()

    def __repr__(self):
        return type_name(type(self))

    def __init_subclass__(cls):
        if type_base(cls) is not SingletonBase:
            m = (f'type {cls.__name__!r} is not an acceptable base type')
            raise TypeError(m)
        SingletonBase.__dict__['__self__'].__self__ = object.__new__(cls)

    def __new__(cls):
        return cls.__self__

    #__bool__ = repeat(False).__next__

new_singleton_type =  SingletonType._make
NullType = new_singleton_type('NULL')
NULL = NullType()
