
# This is the most beautiful scrap of code I've ever seen, let alone written.

class Enumeration:

    '''Remembers the previous value it returned and returns that + 1'''
    
    __slots__ = '__next__'
    
    def __iter__(self):
        return self

    def __new__(cls, i=0):
        
        def __next__(v=None):
            nonlocal i
            if v is not None:
                i = v + 1
                return v
            v = i
            i+= 1
            return v
        
        self = object.__new__(cls)
        self.__next__ = __next__
        
        return self
