if 1:
    from functools import lru_cache
    new_tuple = lru_cache(None)(tuple.__new__)
    class Descropsy(type):
        def __prepare__(name, bases, **kwds):
            return {'__slots__': ()}
        def __call__(cls, descr, self, type):
            return new_tuple(cls, (descr, self, cls))
        def cached(cls, maxsize=None):
            return lru_cache(maxsize)(cls)
    class Descrepit(tuple, metaclass=Descropsy):
        __call__ = property(itemgetter(0))
        descr    = property(itemgetter(0))
        self     = property(itemgetter(1))
        type     = property(itemgetter(2))
    class Tescr(Descrepit):
        __call__ = property(attrgetter("descr.__getitem__"))
    class Test:
        __get__ = Tescr.cached()
        import opcode
        __getitem__ = opcode.opname.__getitem__
        del opcode
    class Obj: f = Test()
    assert Obj.f.descr[9] == 'NOP'
