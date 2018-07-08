class CachedProperty(property):

    def __init__(self, fget:str, *args, **kws):
        if not isinstance(fget, str):
            raise TypeError("fget must be the name where p.cfunc gets bound")
        self._getter_name = fget
        super().__init__(methodcaller(fget), *args, **kws)
        
    @property
    def cfunc(self):
        def wrapped(meth):
            @lru_cache(1)
            def wrapper():
                return meth()
            return wrapper
        return wrapped

    @staticmethod
    def bind_to_cached_property(instance, prop_name, getter):
        '''sets the `fget` of `type(instance)`.`prop_name` to `getter`

        This must be called before a property can be accessed,
        preferably in __init__ or __new__.

        `prop_name` is the name of the CachedProperty owned by
        type(`instance`) that needs a fget.

        `getter` is any callable that takes zero arguments.
        '''

        cls = instance.__class__
        self = getattr(cls, prop_name)
        
        if not isinstance(self, CachedProperty):
            cname = cls.__name__
            raise AttributeError((f'attribute {prop_name!r} of class '
                                  f' {cname!r}is not a CachedProperty'))
        
        wrapper = self.cfunc(getter)
        setattr(instance, self._getter_name, wrapper)

if __name__ == '__main__':
    class ex:
        
        # the "ex" instance will need to call `bind_to_cached_property`
        # at some point before this is accessed it inst.name won't work.
        # '_namegetter' will be where the instance fget is stored
        name = CachedProperty('_namegetter')

        @property
        def game(self):
            # inst.name is ~70% faster than inst.game, not to mention it
            # requires far less boilerplate
            try:
                return self._game
            except AttributeError:
                self._game = self.pensive()
                return self._game
            
        def __init__(self, cls=str):
            # self.pensive will only be called once: the first time self.name is
            # accessed. Functionally identical to ex.game
            CachedProperty.bind_to_cached_property(self, 'name', self.pensive)
            self.cls = cls

        def pensive(self):
            print('looking up self.cls.name ...')
            return self.cls.__name__
    inst = ex()
    assert inst.name == inst.game
    assert inst.name == inst.game
