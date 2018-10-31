
import sys

from functools import partial
from types import *

type_getattr = type.__getattribute__
obj_getattr  = object.__getattribute__
full_dir     = type.__dir__

TD         = vars(type)
TYPE_DIR   = frozenset(TD)
OBJECT_DIR = frozenset(vars(object))

type_mro   = TD['__mro__'].__get__
type_base  = TD['__base__'].__get__
full_dir   = TD['__dir__']          .__get__
type_check = TD['__instancecheck__'].__get__(type, type)
meta_check = TD['__subclasscheck__'].__get__(type, type)

def descr_is_data(obj, hasattr=hasattr):
    return hasattr(obj, '__set__') or hasattr(obj, '__delete__')

def _get_descr(cls, name, meta=type, hasattr=hasattr):
    ns = vars(meta)
    ds = ns.get(name)
    if ds is not None:
        if hasattr(ds, '__get__') or descr_is_data(ds):
            return ds
    if name not in ds and meta_check(meta):
        return _get_descr(type_base(meta))
    raise AttributeError(f'name {name!r} does not refer to a descriptor')
    
def get_descr_get(cls, name, meta=type):
    return _get_descr(cls, name, meta).__get__

def get_descr_set(cls, name, meta=type):
    return _get_descr(cls, name, meta).__set__

def get_descr_del(cls, name, meta=type):
    return _get_descr(cls, name, meta).__delete__

def dro(cls, ob=True, tp=True, metaclass=None):
    'descriptor resolution order'
        
    mro = [*type_mro(cls)]

    if tp:
        if metaclass is None:
            metaclass = type(cls)
        if not isinstance(cls, metaclass):
            raise TypeError('dro() invalid metaclass argument')
        mro[-1:] = type_mro(metaclass)
        
    if not ob:
        mro.pop()
        
    return mro

def _unpack_chained_mappingproxies(cmp):
    return {k:v
            for dict_items in map(MappingProxyType.items, cmp)
            for k,v in dict_items}

def class_dict(cls, ob=True, tp=True, metaclass=None):
    mro = dro(cls, ob, tp, metaclass)
    # note the reversed mro
    return _unpack_chained_mappingproxies(map(vars, reversed(mro)))

def repr_cell(yes, no, ob):
    return yes if ob else no

def show_members(cls, include_meta=False, include_object=True, file=sys.stdout,
                 cell_true='(@)', cell_false='...'):
    '''Prints to `file` a table containing every member of `cls`

    `include_meta` if True will display any accessible metaclass attrs.

    `include_object` if False will hide all attributes inherited
    directly from `object`.
    '''
    if not type_check(cls):
        raise TypeError("show_members() argument must be a class object")
    if len(cell_true) != 3:
        raise ValueError("cell_true must be a 3-character string, not %r"
                         %cell_true)
    if len(cell_false) != 3:
        raise ValueError("cell_false must be a 3-character string, not %r"
                         %cell_false)
    repr_f = partial(repr_cell, cell_true, cell_false)
    
    # get all attributes that can be accessed through the class
    # mro isn't reversed for this call
    mro   = dro(cls, include_object, include_meta)
    ns    = _unpack_chained_mappingproxies(map(vars, mro))
    attrs = sorted(ns)

    # configure the row labels
    roww = max(map(len, ('mro -> ', *attrs)))
    cols = [['mro ->'.rjust(roww, ' '),
             ''.ljust(roww, '-'),
             *(a.ljust(roww, '.') for a in attrs)]]

    # add a column for each class in the calculated mro
    for cls in mro:
        lbl = cls.__name__
        wid = len(lbl)
        stk = []
        add = stk.append

        # populate each cell with a simple true or false indicator
        for cell in map(str, map(repr_f, map(vars(cls).__contains__, attrs))):
            add(cell)
            if len(cell) > wid:
                wid = len(cell)
                
        # align the columns
        col = [lbl.ljust(wid, ' ')] 
        col+= ['-'.ljust(wid, '-')] 
        col+= [cel.center(wid,'.') for cel in stk] 
        cols.append(col)
        
    s = {1:'-+-'.join}.get
    x = ' | '.join
    for i, row in enumerate(zip(*cols)):
        print(s(i, x)(row), file=file)
