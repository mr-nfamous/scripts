class SlotSetter(tuple):

    '''SlotSetter(*slots, getter=None, deleter=None)
    Turns cls.__slots__ into a slot setter

    If provided, a getter and deleter will be added to the class as
    `getter` and `deleter`, respectively.

    If `erase` is True, removes the descriptors from the class's dict.
    '''

    def __new__(cls, *args, getter=None, deleter=None, erase=False):
        self = tuple.__new__(cls, args)
        self.erase = erase
        self.setter = None
        self.getter = getter
        self.deleter = deleter
        self.__objclass__ = None
        return self

    def __get__(self, instance, cls):
        if instance is None:
            return self
        return self.fset(instance, cls)

    def __set_name__(self, cls, name):
        self.__objclass__ = cls
        self.slots = {s: cls.__dict__[s] for s in self}
        self.setters = setters = {s: getattr(cls, s).__set__ for s in self}
        self.deleters= deleters = {s: getattr(cls, s).__delete__ for s in self}
        self.getters = getters = {s: getattr(cls, s).__get__ for s in self}

        name = cls.__name__

        def fset(o, attr, value):
            setters[attr](o, value)

        def fdel(o, attr):
            deleters[attr](o)

        def fget(o, attr):
            return getters[attr](o)

        fset.__qualname__ = fset.__name__ = f'{name}_slot_setter'
        fdel.__qualname__ = fdel.__name__ = f'{name}_slot_deleter'
        fget.__qualname__ = fget.__name__ = f'{name}_slot_getter'

        self.fset = fset.__get__
        self.fdel = fdel.__get__
        self.fget = fget.__get__

        if self.setter is not None:
            setattr(cls, self.setter, fget)

        if self.getter is not None:
            setattr(cls, self.getter, fget)

        if self.deleter is not None:
            setattr(cls, self.deleter, fdel)

        if self.erase:
            for slot in self:
                delattr(cls, slot)

    def __repr__(self):
        return f'{type(self).__name__}{tuple.__repr__(self)}'
