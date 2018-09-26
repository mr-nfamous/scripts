
MAX_SUBCLASSES_RECURSION_DEPTH = 4095
MOST_SUBCLASSES = 100000

def itersubs(cls, f= type.__dict__['__subclasses__'].__get__):
    return f(cls)()

def recursive_subclasses(most_base):
    a = {most_base}
    b = {*itersubs(most_base)}
    r = {*a}    
    update = r.update
    depth = 0
    size = r.__len__
    while 1:
        if not a:
            return r
        update(b)
        a, b = b, set()
        for base in a:
            b.update(itersubs(base))
        depth += 1
        if depth > MAX_SUBCLASSES_RECURSION_DEPTH:
            raise RecursionError("got stuck on something")
        if size() > MOST_SUBCLASSES:
            raise TypeError(f'subclass list at {size()} classes which is more '
                            f'than MOST_SUBCLASSES ({MOST_SUBCLASSES:_})')
