
"""Set of utilities to manage the way a module is exported

Detailed error messages make finding issues easy.

Works in both Python 2.7 and 3.6.

Functions:

------
@public(*objects:[str, object], overwrite=False) -> objects[0]:
------
    Mark objects (or names) as public and automatically append
    them to __all__.

    There are 2 different ways to use it:
        @public(overwrite=False) <- (with or without parentheses)
            Simple decorator for function/class definitions. Adds the
            wrapped object's __name__ attribute to __all__.

        public(object_or_name, *objects_or_names, overwrite=False)
            If an object is passed as an argument, all names that refer
            to that object will be added to __all__. If a string is
            passed, the name will be added assuming the reference
            actually exists.

----------------
public_constants(**constants) -> constants:
----------------
    Define public global variables, adding their names to __all__.

------------------
public_from_import(module, *names) -> {**imported}:
------------------
    `from module import names` and add the imported names to __all__.

--------------
publish_module(module) -> module:
    Publish everything that would be gotten with `from module import *`

----------------
safe_star_import(module) -> {**imported}
----------------
    `from module import *` that will not overwrite existing names

-----------
star_import(module,
----------- overwrite=False,
            ignore_private=False,
            ignore_metadata=True) -> {**imported}:
    Ignore default * import mechanics to import almost everything.

    If overwrite is False, an error is raised instead of overwriting.

    If ignore_private is True, then _private names prepended with an
    underscore are ignored.

    If ignore_metadata is False, then module metadata attributes
    such as __author__ and __version__ are imported.

    Special attributes of modules such as __path__, __file__,
    and __all__ are never imported.

-------------------
reverse_star_import(module, ignore=set())
-------------------
    Remove what would be imported with from module import *
    Objects that have been renamed after being imported are not removed.
    The most useless function ever created.

---------------
reimport_module(module) -> module:
---------------
    Clear module's dict and reimport it.
"""

from __future__ import print_function, with_statement, unicode_literals

__author__ = 'Dan Snider'
__version__ = '1.3.0'

import functools
import importlib
import sys
import __main__
from types import ModuleType
from operator import attrgetter, methodcaller

if sys.version_info < (3,):
    from __builtin__ import xrange as range
    from imp import reload as _reload
    from itertools import (ifilterfalse as filterfalse,
                           imap as map,
                           izip as zip,
                           ifilter as filter,
                           groupby)
    dict_items = dict.viewitems
    dict_keys = dict.viewkeys
    dict_values = dict.viewvalues
else:
    from importlib import reload as _reload
    from itertools import filterfalse, groupby
    dict_items = dict.items
    dict_keys = dict.keys
    dict_values = dict.values
    basestring = str

_is_string = basestring.__instancecheck__
_is_module = ModuleType.__instancecheck__
_is_list = list.__instancecheck__
_get_frame = sys._getframe
_get_module = sys.modules.get
_STAR_IMPORT_IGNORE = frozenset((
    '__cached__',
    '__doc__',
    '__loader__',
    '__name__',
    '__package__',
    '__spec__',
    '__file__',
    '__builtins__',
    '__all__',
    '__path__',
    ))
_METADATA = frozenset((
    '__about__',
    '__annotations__',
    '__author__',
    '__authors__',
    '__contact__',
    '__copyright__',
    '__credits__',
    '__date__',
    '__debug__',
    '__deprecated__',
    '__email__',
    '__import__',
    '__license__',
    '__maintainer__',
    '__revision__',
    '__status__',
    '__version__',
    ))
_SCOPES = {}
_SCOPE_PICKLES = set()
_SENTINEL = object()

class Scope(object):

    """Scope(module)"""
    __slots__ = ('_module', '_all')
    __getitem__ = property(attrgetter('_module.__dict__.__getitem__'))
    __contains__ = property(attrgetter('_module.__dict__.__contains__'))
    __len__ = property(attrgetter('_module.__dict__.__len__'))
    module_name = property(attrgetter('_module.__name__'))
    get_item = property(attrgetter('_module.__dict__.get'))
    namespace = property(attrgetter('_module.__dict__'))

    @property
    def _modifiable(self):
        return _SCOPES.get(self._module) is self

    @classmethod
    def is_modifiable(cls, module):
        return _SCOPES.get(module) is not None

    def __new__(cls, module, new_object=object.__new__):
        module = validate_module(module)
        name = module.__name__
        if name in _SCOPE_PICKLES:
            raise TypeError('%r is currently pickled'%module.__name__)
        if module in _SCOPES:
            raise TypeError('%r is already being modified'%module.__name__)
        self = new_object(cls)
        self._module = module
        self._all = None
        return self

    def check_modifiable(method):
        @functools.wraps(method)
        def wrap(self, *args, **kws):
            if _SCOPES.get(self._module) is not self:
                raise TypeError('Scope of %s is read-only.'%self.module_name)
            return method(self, *args, **kws)
        return wrap

    def __enter__(self):
        module = self._module
        name = module.__name__
        if name in _SCOPE_PICKLES:
            raise TypeError('%r is pickled and cannot be modified'%name)
        if module in _SCOPES:
            raise ValueError('%r is already being modified'%self.module_name)
        __all__ = validate_all(self._module)
        self._all = [] if __all__ is None else __all__
        return _SCOPES.setdefault(self._module, self)

    @check_modifiable
    def __exit__(self, *args):
        module = self._module
        __all__ = self._all
        if _is_list(__all__):
            module.__all__ = sorted(set(__all__))
        elif __all__ is not None:
            raise ValueError('%r ended up with an invalid __all__ attribute'
                             %self.module_name)
        _SCOPES.pop(module)

    @check_modifiable
    def __setitem__(self, key, value):
        self._module.__dict__[key] = value

    @check_modifiable
    def __delitem__(self, key):
        del self._module.__dict__[key]

    @check_modifiable
    def extend_all(self, elems):
        if set(elems) - dict_keys(self._module.__dict__):
            args = ', '.join(map(repr, uniques)), self.module_name
            raise NameError('names %s do not exist in %s'%args)
        return self._all.extend(elems)

    @check_modifiable
    def update_namespace(self, d=(), **kws):
        """module.__dict__.update(d, **kws)"""
        return self._module.__dict__.update(d, **kws)

    def keys(self):
        return dict_keys(self._module.__dict__)

    def values(self):
        unique = []
        append = unique.append
        for elem, group in groupby(dict_values(self.namespace)):
            if elem not in unique:
                append(elem)
        return unique

    @classmethod
    def repair_all(cls, module):
        """Clear invalid entries in module.__all__"""
        pop = module in _SCOPES
        self = _SCOPES[module] if pop else cls(module)
        __all__ = getattr(self._module, '__all__', None)
        if __all__ is not None:
            if not _is_list(__all__):
                if hasattr(__all__, 'index'):
                    __all__ = list(__all__)
            __all__ = list(filter(self.keys().__contains__, __all__))
            self._all = module.__all__ = __all__
        if pop:
            _SCOPES.pop(module, None)

    def update(self, d=(), **kws):
        d = dict(d, **kws)
        self.update_namespace(d)
        self.extend_all(d)

    def find_refs(self, item):
        """Find all references to `item` in scope's namespace"""
        for name, value in dict_items(self._module.__dict__):
            if value is item:
                yield name

    def list_imported_names(self, other):
        """Find all names that have been imported from `other`"""
        if isinstance(other, type(self)):
            b = other.namespace
        else:
            b = validate_module(other).__dict__
        a = self._module.__dict__
        imported = dict_keys(a) & dict_keys(b)
        return [k for k in imported if a[k] is b[k]]

    def get_star_imports(self):
        """What's gotten with from module import *"""
        __all__ = validate_all(self._module)
        if __all__ is None:
            return set(iter_public_names(self._module))
        return set(__all__)

    def close(*args):
        if len(args) >= 2:
            module_or_instance = args[1]
        elif len(args) == 1:
            module_or_instance = args[0]
        else:
            raise TypeError('close needs a Scope instance or a module')
        if _is_module(module_or_instance):
            module = validate_module(module_or_instance)
        else:
            module = module_or_instance._module
        self = _SCOPES.get(module)
        if self is not None:
            self.__exit__()

    def __iter__(self):
        return iter(self.keys())

    def __copy__(self):
        raise TypeError('%s cannot be copied'%self.__class__.__name__)

    def __deepcopy__(self, memo):
        raise TypeError('%s cannot be deepcopied'%self.__class__.__name__)

    def __reduce__(self):
        module = self._module
        name = module.__name__
        if _get_module(name) is not module:
            raise ValueError('cannot pickle modules not in sys.modules')
        entered = module in _SCOPES
        instance = _SCOPES.pop(module, self)
        args = (name, self._all, entered)
        _SCOPE_PICKLES.add(name)
        return self._build, args

    @classmethod
    def _build(cls, name, __all__, entered):
        if name not in _SCOPE_PICKLES:
            raise TypeError('%r is no longer pickled'%name)
        module = validate_module(name)
        instance = object.__new__(cls)
        instance._module = module
        _SCOPE_PICKLES.remove(name)
        if entered:
            instance._all = __all__
            self = _SCOPES.setdefault(module, instance)
            if _SCOPES[module] is not self:
                raise TypeError('Scope %r was somehow created even though it '
                                'was already pickled'%name)
            return self
        return instance

    def __repr__(self):
        return '<%s.__all__: %s>'%(self.module_name, self._all)

def _navframe(frame):
    while True:
        try:
            print(frame.f_globals['__name__'])
            frame = frame.f_back
        except:
            return

class InvalidAllError(Exception):
    pass

def validate_all(module):
    """See if a module has a valid __all__ attribute"""
    __all__ = getattr(module, '__all__', _SENTINEL)
    if __all__ is _SENTINEL:
        return None
    if hasattr(__all__, 'index'):
        if all(map(_is_string, __all__)):
            import_list = set(__all__)
            if import_list.issubset(dict_keys(module.__dict__)):
                return __all__[:]
            error = InvalidAllError('module %r has names in its __all__ that '
                                    "don't actually exist"%module.__name__)
        else:
            error = InvalidAllError('module %r has an __all__ containing '
                                    'invalid types'%module.__name__)
    else:
        error = InvalidALlError('module %r has an __all__ that is not '
                                'indexable so it cannot be used for star '
                                'imports'%module.__name__)
    raise error

def validate_module(module_or_name):
    if _is_string(module_or_name):
        module = sys.modules.get(module_or_name, _SENTINEL)
        if module is _SENTINEL:
            module = importlib.import_module(module_or_name)
    else:
        module = module_or_name
    if not _is_module(module):
        raise TypeError('%r is not a module or string'%module_or_name)
    return module

is_not_public_name = methodcaller('startswith', '_')

def iter_public_names(module):
    """Iterate over all public attributes of `module`"""
    return filterfalse(is_not_public_name, validate_module(module).__dict__)

def iter_dunder_names(module):
    """Iterate over all dunder attributes of `module`"""
    for k in validate_module(module).__dict__:
        if k[:2] == '__' and k[-2:] == '__' and len(k) > 3:
            yield k

def iter_private_names(module):
    """Iterate over all private attributes of `module`"""
    for k in validate_module(module).__dict__:
        if k and k[0] == '_':
            if len(k) < 4 or (not (k[-2:] == '__' and k[:2] == '__')):
                yield k

def get_module_from_filename(file):
    """Find the module that corresponds to `file`"""
    file = file.lower()
    lower = methodcaller('lower')
    for name, module in dict_items(sys.modules):
        module_file = getattr(module, '__file__', None)
        if module_file and lower(module_file) == file:
            return validate_module(module)
    raise ValueError('no module found with the filename %r'%file)

def get_full_name(obj):
    name = getattr(obj, '__qualname__', obj.__name__)
    if hasattr(obj, '__module__'):
        return '%s.%s'%(obj.__module__, name)
    return name

def hex_id(obj, nibs=((sys.maxsize.bit_length()+7)//8) * 2):
    return '0x{:0{nibs}X}'.format(id(obj), nibs=nibs)

def generic_repr(obj):
    objtype = 'class' if obj.__class__ is type else obj.__class__.__name__
    try:
        return '<%s %s at %s>' % (objtype, get_full_name(obj), hex_id(obj))
    except:
        return safe_repr(obj)

def safe_repr(obj, maxlen=50):
    obj_repr = repr(obj)
    if len(obj_repr) < maxlen:
        return obj_repr
    obj_repr = obj_repr[:maxlen]
    return '<%s object %s at %s>'%(type(obj).__name__, obj_repr, hex_id(obj))

def _get_calling_module(depth=0, *args, **kws):
    """Get the module that invoked a function"""
    return _get_module(_get_frame(2+depth).f_globals.get('__name__'))

def _validate_kws(kws):
    for kw in kws:
        args = (kw, _get_frame(1).f_code.co_name)
        error = TypeError('%r is not a valid kw argument for function %r'%args)
        raise error

def _public(module, *objects, **kws):
    overwrite = kws.pop('overwrite', False)
    _validate_kws(kws)
    validated = {}
    update = validated.update
    with Scope(module) as context:
        for ob in objects:
            if _is_string(ob):
                update(_validate_public_alias(ob, context))
            else:
                update(_validate_public_object(ob, context,  overwrite))
        context.update(validated)
    return objects[0]

def _validate_public_alias(ob, context):
    if ob in context.keys():
        return {ob: context.namespace[ob]}
    else:
        raise NameError('module %r has no attribute %r to publish'
                        %(context.module_name, ob))

def _validate_public_object(ob, context, overwrite):
    refs = [k for k, v in dict_items(context.namespace) if v is ob]
    if not refs:
        ob_name = getattr(ob, '__name__', _SENTINEL)
        if ob_name is _SENTINEL:
            ob_name = None
        if _is_string(ob_name):
            val = context.get_item(ob_name, ob)
            if (val is ob) or overwrite:
                return {ob_name: val}
            else:
                args = context.module_name, ob_name, generic_repr(val)
                raise ValueError("'%s.%s' is already public as %s"%args)
        else:
            raise NameError('in module %r there is no name for %s'
                             %(context.module_name, safe_repr(ob)))
    return dict.fromkeys(refs, ob)

def public(*objs, **kws):
    """Register objects to __all__ automatically

    Unless `overwrite` is True, two distinct objects with the same name
    will raise an error, otherwise the latter will replace the former.
    """
    module = _get_calling_module()
    if not objs:
        return lambda *objects: _public(module, *objects, **kws)
    return _public(module, *objs, **kws)

public(public)

def public_alias(*args):
    """Deprecated"""
    return public(*args)

@public
def public_constants(**constants):
    """Define public global variables and return them in a new dict"""
    with Scope(_get_calling_module()) as context:
        for k in dict_keys(constants) & context.keys():
            if context[k] is not constants[k]:
                args = context.module_name, k, generic_repr(context[k])
                raise ValueError("'%s.%s' is already public as %s"%args)
        context.update(constants)
    return constants

@public
def safe_star_import(module):
    """Make sure a star import doesn't overwrite anything"""
    module = validate_module(module)
    caller = _get_calling_module()
    with Scope(caller) as context, Scope(module) as imported_context:
        import_list = imported_context.get_star_imports()
        for name in context.keys() & import_list:
            args = context.module_name, name, generic_repr(context[name])
            raise NameError('%s.%s already exists as %s'%args)
        imported = {k: imported_context[k] for k in import_list}
        context.update_namespace(imported)
    return imported

@public
def star_import(module, **kws):
    """Ignores default * import mechanics to import almost everything

    If `overwrite` is True, allow the import to replace any names that
    already exist instead of raising an error.

    If `ignore_private` is set to True, _sunder (private) names will
    not be imported.

    Names that already exist in the calling module's namespace will
    be overwritten if `overwrite` is set to True, otherwise an error
    will be raised.

    Items in `ignore_list` will not be imported.

    If `ignore_metadata` is not true, even common metadata attributes
    will be imported.
    """
    module = validate_module(module)
    ignore_metadata = kws.pop('ignore_metadata', True)
    ignore_private = kws.pop('ignore_private', False)
    overwrite = kws.pop('overwrite', False)
    ignore_list = _METADATA if ignore_metadata else set()
    ignore_list |= set(kws.pop('ignore_list', ())) | _STAR_IMPORT_IGNORE
    _validate_kws(kws)
    caller = _get_calling_module()
    with Scope(caller) as context, Scope(module) as imported_context:
        if ignore_private:
            import_list = iter_public_names(module)
        else:
            import_list = imported_context.keys() - ignore_list
        if not overwrite:
            for name in import_list & context.keys():
                old, new = context[name], imported_context[name]
                if old is new:
                    continue
                current_ob = generic_repr(context[name])
                imported_ob = generic_repr(imported_context[name])
                module_name = context.module_name
                imported_name = imported_context.module_name
                args = imported_name, name, imported_ob, name, current_ob
                error = ImportError('tried importing %s.%s as %s but '
                                    '%r already exists as %s'
                                    %args)
                raise error
            else:
                import_list -= context.keys()
        imported = {k:imported_context[k] for k in import_list}
        context.update_namespace(imported)
    return imported

@public
def public_from_import(module_or_name, *names, **kws):
    """Publicly import names from module and return them in a new dict"""
    overwrite = kws.pop('overwrite', False)
    _validate_kws(kws)
    module = validate_module(module_or_name)
    caller = _get_calling_module()
    with Scope(caller) as context, Scope(module) as imported_context:
        import_list = set(names)
        for name in import_list - imported_context.keys():
            args = module.__name__, name
            raise ImportError('module %r has no attribute %r'%args)
        imported = {k:imported_context[k] for k in import_list}
        if not overwrite:
            for name, value in dict_items(imported):
                if context.get_item(name, value) is not value:
                    args = context.module_name, name, generic_repr(ns[name])
                    raise ValueError("'%s.%s' is already public as %s"%args)
        context.update(imported)
    return imported

@public
def publish_module(module, **kws):
    """Publish everything you would get with `from module import *`

    If `overwrite` is True, allow the import to replace any names that
    already exist instead of raising an error.
    """
    overwrite = kws.pop('overwrite', False)
    _validate_kws(kws)
    caller = _get_calling_module()
    module = validate_module(module)
    with Scope(caller) as context, Scope(module) as imported_context:
        import_list = imported_context.get_star_imports()
        if not overwrite:
            for name in context.keys() & import_list:
                if context[name] is imported_context[name]:
                    continue
                raise ImportError('%r already exists'%name)
        context.update({k: imported_context[k] for k in import_list})
    return module

@public
def reverse_star_import(module_or_name, ignore=None):
    """Remove what would be imported with from module import *"""
    module = validate_module(module_or_name)
    caller = _get_calling_module()
    try:
        ignore = set() if ignore is None else set(ignore)
    except TypeError:
        raise TypeError('ignore must be a list of names not to be deleted')
    with Scope(caller) as context, Scope(module) as imported_context:
        for name in ignore - context.keys():
            error = NameError('%r has no attribute %r to keep from being '
                              'deleted'%(context.module_name, name))
            raise error
        for name in imported_context.get_star_imports() - ignore:
            if context[name] is imported_context[name]:
                del context[name]

@public
def reimport_module(module_or_name, reloader=_reload):
    """Clear module's dict and reimport it"""
    module = validate_module(module_or_name)
    name = module.__name__
    module.__dict__.clear()
    module.__name__ = name
    return reloader(module)
