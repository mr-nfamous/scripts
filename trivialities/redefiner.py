
import weakref
from operator import setitem
from sys import _getframe as GF

NULL = 0.0

class redefinition:

    __slots__ = '__weakref__', 'dict', 'name', 'prev'

    cache = weakref.WeakValueDictionary()
    
    def __new__(cls, dict, name, prev=NULL):
        
        key = (id(dict), name, id(prev))
        ref = cls.cache.get(key)
        
        if ref is None:
            cls.cache[key] = ref = object.__new__(cls)
            ref.dict = dict
            ref.name = name
            ref.prev = prev
            
        return ref
        
    def __del__(self):

        if self.prev is not NULL:
            self.dict[self.name] = self.prev
            
        elif self.name in self.dict:
            del self.dict[self.name]

class Redefiner:
    
    '''Decorator that moves the decorated object to another namespace

    If another object previously was bound to the decorated object's
    name, that same object still be there after the decorator has
    finished.
    '''
    
    def __init__(self, at):
        self.__dict__ = at

    def __call__(self, obj):

        '`obj` will be defined in f.__dict__[obj.__name__]'''

        key = obj.__name__
        loc = GF(1).f_locals
        
        if key in loc:
            old = loc[key]
        else:
            old = NULL

        temp = redefinition(loc, key, old)
        
        setattr(self, key, obj)
        setitem(loc, key, temp)

        return None

if __name__ == '__main__':
    
    from types import ModuleType
    
    dummy = ModuleType('dummy')
    for_dummy = Redefiner(vars(dummy))

    dumb_msg = 'NOT dummy.Dub'
    Dumb = dumb_msg
    
    @for_dummy
    class Dumb(dict):
        
        def closure(fast_attr=Redefiner(vars())):

            dict_attr = dict.__getattribute__

            @fast_attr
            def __missing__(self, key):
                try:
                    return dict_attr(self, key)
                except AttributeError:
                    raise KeyError(key) from None
            
        closure()

    assert Dumb is dumb_msg
#    assert 'Dumb' not in globals()
    d = dummy.Dumb()
    d.x = 'x'
    print(d['x'])
    
