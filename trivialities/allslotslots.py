
# It is a nightmare to try and add certain slots and I could never
# figure it out until now. The solution is: all of the problem causing
# slots must be added at once.

# However, __module__ is still never added (even though it actually
# allocates space for the member in the new type's struct...) so this
# proxy property workaround is the only way.

if __name__ is __name__:
    class A:
        __slots__ = ('__dict__',
                     '__doc__',
                     '__module_proxy__',
                     '__name__',
                     '__qualname__',
                     '__weakref__')
        __module__ = property()
        del __qualname__
        
    prox = A.__dict__['__module_proxy__']        

    A.__dict__['__module__'].__init__(
        prox.__get__,
        prox.__set__,
        prox.__delete__
    )
    
    del A.__slots__
    del A.__module_proxy__
    for k,v in sorted(vars(A).items()):
        print(f'{k} = {v!r}')
        
    o = A()
    o.__doc__ = {1,2,3}
    o.__module__ = {len:str}
    o.__name__ = 'NOTHING'
    o.__qualname__ = float('inf')
    o.burrow_into_dict = 99
    print(o.__dict__)
    print('module =', o.__module__)
