
'''
cachedproperty

A CachedProperty is associated with two names:

* the key in the dict of its owner's class where the actual property lives;
* and the instance attribute (slot/dict key) where its per-instance fget lives

class MyClass:

    a = CachedProperty("calculate_a")

    @CachedProperty('b_impl')
    def b(self):
        return self.a + self.b

In `MyClass`, the property's name is "a" and every instance of MyClass must
have an instance attribute named "calculate_a" that holds a callable taking
zero arguments before it can be accessed.

With `MyClass.b` this is taken care of automagically since the function
"b" is remembered by the CachedProperty instance that "overwrites" it.
It can do so by wrapping the class's __init__ method to initialize all
CachedProperties with their stored implementation functions.

Note that property fget initializations occurs *before* the class's
own __init__ function executes (assuming it has one).

Here's how using CachedProperties affected the performace of the example
classes defined below (numbers are as nanosecond per call):
    
                  init   i.volume
i=Box(10, 4, 3)    803        252
i=Cube(10, 4, 3)  4445        120

In that case, you would need 25-30 property accesses to break even after
the steep initialization penalty incurred with CachedProperty.
That penalty definitely limits its viability for the vast majority of
use cases, but when it actually makes sense to use it can easily double
the performance of the vanilla property caching method.

This could have been accomplished in C in half the time and with 3x
the speed...
'''

import weakref
from functools import cowraps
from itertools import starmap, cycle
from operator import methodcaller

_NOARGS = ((),)

def empty_fget(*args, **kws):
    error = AttributeError("CachedProperty hasn't been bound to instance yet")
    raise error

def init_wrapper(__init__, owner, cache):
    '__init__ wrapper binding getter descriptor on instances of owner'

    # CachedProperty has the following attributes:
    # * owne      -> weak reference to class that owns the property
    # * name      -> key in owner class __dict__ where property lives
    # * fget_impl -> a descriptor implementing getter behavior
    # * impl_name -> name of owner instance attr where descriptor stored

    # only properties with a fixed fget_impl will be in the cache which
    # allows for late binding.
    # Otherwise, this initialized them automagically

    cache_items = cache.items()
    if __init__ is object.__init__ :
        # optimization for classes using __new__ in lieu of __init__
        def __init__(self, *args, **kws):
            for impl_name, fget_impl in cache_items:
                fget = fget_impl.__get__(self, owner)
                impl = cycle(starmap(fget, _NOARGS)).__next__
                setattr(self, impl_name, impl)

    else:
        f = __init__
        @wraps(f)
        def __init__(self, *args, **kws):

            for impl_name, fget_impl in cache_items:
                fget = fget_impl.__get__(self, owner)
                impl = cycle(starmap(fget, _NOARGS)).__next__
                setattr(instance, impl_name, impl)

            f(self, *args, **kws)

    return __init__

class CachedProperty(property):

    def __init__(self, fget, *args, **kws):

        assert isinstance(fget, str), "probably forgot ('IMPL_NAME')"

        self.impl_name = fget
        self.fget_impl = empty_fget
        self.owner     = None
        super().__init__(methodcaller(fget))
        
    def __set_name__(self, cls, name):

        self.owner = weakref.ref(cls)
        self.name  = name
        fget_impl  = self.fget_impl
        if fget_impl is not empty_fget:
            self.update_cache(cls, self.fget_impl)

    def __call__(self, fget):
        # enables delayed binding and usage as a decorator

        if self.fget_impl is not empty_fget:
            raise TypeError(f'{self!r} already has a getter')
        if fget is None:
            raise TypeError(f'{self!r} requires a getter')
        owner = self.owner
        if owner is not None:
            self.update_cache(owner(), fget)
        else:
            self.fget_impl = fget
        return self

    def getter(self, f):
        raise TypeError('cannot use CachedProperty.getter to define fget')

    def update_cache(self, cls, fget_impl):

        impl_name = self.impl_name
        __init__ = cls.__init__
        cache = getattr(__init__, '_cached_properties_', None)

        if cache is None:
            cache = {}
            wrapped = init_wrapper(__init__, cls, cache)
            wrapped._cached_properties_ = cache
            cls.__init__ = wrapped

        if fget_impl is not None:
            self.fget_impl = cache[impl_name] =  fget_impl

    @classmethod
    def bind(cls, instance, prop_name, impl):
        '''Set the `prop_name` fget for `instance` as `impl`

        Only works when the instance doesn't have a current working
        implementation, which could only happen if CachedProperty
        was used in an atypical manner, ie. not as a decorator in
        the form of:
        
        >>> @CachedProperty("_volume_impl")
        >>> def volume(self):
        >>>    ...

        Will fail when used more than once per instance.
        '''

        self = instance.__class__.__dict__[prop_name]
        impl_name = self.impl_name
        
        if hasattr(instance, impl_name):
            raise TypeError("CachedProperty() already bound")
        
        f = cycle(starmap(impl, _NOARGS)).__next__
        setattr(instance, impl_name, f)

if __name__ == '__main__':
    try:
        from stex import e
    except:
        pass
    class Box:

        def __new__(cls, w, h, d):
            self = object.__new__(cls)
            self.w = w
            self.h = h
            self.d = d
            return self

        @property
        def surface_area(self):
            try:
                a = self._area
            except:
                w, h, d = self.w, self.h, self.d
                a = self._area = 2 * (w*h + d*h + w*d)
            return a

        @property
        def volume(self):
            try:
                v = self._volume
            except:
                w, h, d = self.w, self.h, self.d
                a = w * h
                S = self.surface_area
                v = self._volume = ((S - 2*a) * a) / ((w+h) * 2)

            return v

    class Cube:

        def __new__(cls, w, h, d):
            self = object.__new__(cls)
            self.w = w
            self.h = h
            self.d = d
            return self

        @CachedProperty("_surface_area_impl")
        def surface_area(self):
            w, h, d = self.w, self.h, self.d
            r = 2 * (w*h + d*h + w*d)
            return r

        @CachedProperty('_volume_impl')
        def volume(self):

            w, h, S = self.w, self.h, self.surface_area
            a = w * h

            r = ((self.surface_area - 2*a) * a) / ((w+h) * 2)
            return r
