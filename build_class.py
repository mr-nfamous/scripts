import ast
import parser
import sys

from functools import lru_cache

_CLASS_BODY_EXECUTOR = (
    parser.suite(
    r'class_dict["__classcell__"] =eval(class_body, f_globals, class_dict)')
).compile()
function = type(lambda:0)
code     = type(_CLASS_BODY_EXECUTOR)

tp_prepare  = type.__prepare__
tp_dict     = type.__dict__['__dict__'].__get__
tp_check    = type.__instancecheck__.__get__
t           = tp_dict(type)
tp_mro      = t['__mro__'].__get__
tp_name     = t['__name__'].__get__

is_ast_node    = tp_check(ast.AST)
is_class       = tp_check(type)
str_check      = tp_check(str)
function_check = tp_check(function)
code_check     = tp_check(code)


@lru_cache()
def PyType_IsMapping(tp):
    # The only way to be sure if the BINARY_SUBSCRIPT opcode
    # could work is to emulate the way the interpter looks up the
    # mp_subscript slot and that process bypasses all attribute hoooks.
    for base in tp_mro(tp):
        dict = tp_dict(tp)
        if '__getitem__' in dict:
            return True
    return False


def calculate_metaclass(meta, bases):
    for metaclass in map(type, bases):
        if issubclass(meta, metaclass):
            continue
        if not issubclass(metaclass, meta):
            raise TypeError("incompatible metaclass layout")
        meta = metaclass
    return meta


def _esoteric_source(src):
    if str_check(src):
        return parser.suite(src).compile()
    if is_ast_node(src):
        if isinstance(src, ast.ClassDef):
            node = ast.Module([src])
        elif (isinstance(src, ast.Module) and
              isinstance(src.body[0], ast.ClassDef)):
            node = src
        else:
            raise TypeError(f'build_class() using an ast node as the '
                                f'class body it must be a ast.Class node '
                                f'or an ast.Module node whose .body[0] is '
                                f'a Class')
        return compile(node, '<ast.Class>', 'exec')
    if isinstance(src, (tuple, list)):
        src = parser.sequence2st(src)
    if isinstance(src, parser.STType):
        if not parser.issuite(src):
            raise TypeError(f'build_class() the parser syntax tree objects '
                            f'must be a "suite"')
        return parser.compilest(src)


def exec_class_body(class_body, class_dict, f_globals=None):
    'Populate the mapping `class_dict` by executing `class_body`'
    f_globals = f_globals or sys._getframe(1).f_globals
    exec(_CLASS_BODY_EXECUTOR, f_globals, vars())
    if class_dict['__classcell__'] is None:
        del class_dict['__classcell__']


def build_class(source, name, *bases, **kwds):
    ''' Emulate builtins.__build_class__ from within Python
   
    Executes any code-like object that can usually be used to
    generate modules or classes. A generalization is that the code must
    use LOAD_NAME/SET_NAME opcodes which the compiler only uses for 
    modules and class bodies. The co_flags are usually 0 or 64 but
    it may not matter (or arbitrary flags may crash the interpreter, who
    knows).
   
    Note: code objects with co_freevars (aka those with LOAD_CLASSDEREF)
    will not work. The only circumstances that opcode is generated is
    when a class nested in a function references a freevariable in the
    function (ie, pretty much never).

    Perhaps one day, eval will be updated to accept closures. Or maybe
    there is a way to explicitly create frame objects from the Python
    layer already (or at least modify frame.f_gocals without ctypes...)
    '''

    f_context = sys._getframe(1)

    if function_check(source):
        class_body = source.__code__
    elif code_check(source):
        class_body = source
    else:
        print('yh generic')
        class_body = _esoteric_source(source)

    metaclass = kwds.pop('metaclass', None) or (bases or None)

    if metaclass is None:
        metaclass = type
        bases     = object,
    else:
        if metaclass is bases:
            metaclass = type(bases[0])
        if bases:
            if is_class(metaclass):
                metaclass = calculate_metaclass(metaclass, bases)
        else:
            bases = object,

    # interesting trivia: type.__prepare__ is by far the fastest
    # way to programatically generate an empty dictionary. It's
    # at least twice as fast as the dict constructor, even when
    # referenced from locals or freevars.
    dict_prep = getattr(metaclass, '__prepare__', tp_prepare)
    classdict = dict_prep(name, bases, **kwds)

    if not PyType_IsMapping(type(classdict)):
        error = TypeError(
            "%.200s.__prepare__() must return a mapping, not %.200s",
            tp_name(metaclass if is_class(metaclass) else type(metaclass)),
            tp_name(type(classdict)))
        raise error

    f_globals = sys._getframe().f_globals
    exec_class_body(class_body, classdict, f_globals)
    return metaclass(name, bases, classdict)

