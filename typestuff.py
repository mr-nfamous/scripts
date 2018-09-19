

__all__ = ['load_tp_slots']
from sys import _getframe as GF

getters = {}
setters = {}
deleters = {}

for dname, fname, descr in [(k, k.strip('_'), v)
                            for k, v in type.__dict__.items()
                            if hasattr(v, '__get__') and k.startswith('__')]:
    getters[f'type_{fname}'] = descr.__get__
    if hasattr(descr, '__set__'):
        setters[f'set_tp_{fname}'] = descr.__set__
        deleters[f'del_tp_{fname}'] = descr.__delete__


del dname, fname, descr


def load_tp_slots(get=True, set=False, delete=False):
    ns = GF(1).f_globals
    if get:
        ns.update(getters)
    if set:
        ns.update(setters)
    if delete:
        ns.update(deleters)

load_tp_slots()

