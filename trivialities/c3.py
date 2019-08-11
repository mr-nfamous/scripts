def c3(*bases):
    tp_bases = type.__dict__['__bases__'].__get__
    def path(t):
        yield t
        for base in tp_bases(t):
            yield from path(base)
    d = {}
    for b in bases:
        for t in path(b):
            if t in d:
                del d[t]
            d[t]=0
    return (*d,)
