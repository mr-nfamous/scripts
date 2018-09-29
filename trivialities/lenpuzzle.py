from operator import attrgetter as AG, methodcaller as MC, itemgetter as IG
class who:
    __slots__ = '_items'

    def __init__(self):
        self._items = [0,4]

    _lena__ = property(AG('_items.__getitem__'))
    _lenb__ = property(MC('_lena__', -1))  
    __len__ = property(AG('_lenb__.__pos__'))
