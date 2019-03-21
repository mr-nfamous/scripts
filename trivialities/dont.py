class dont(dict):

    __slots__ = '__missing__', 'contains', 'getitem'

    def __init__(self, func, *args):
        if args:
            func         = partial(func, *args)
        self.__missing__ = lambda k: s(k, func(k))
        setdefault       = s = dict.setdefault  .__get__(self)
        self.getitem     =     dict.__getitem__ .__get__(self)
        self.contains    =     dict.__contains__.__get__(self)

