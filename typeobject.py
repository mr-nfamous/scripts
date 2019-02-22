def object_getattro(ob, name,
                    Py_TYPE       = type,
                    TP_MRO        = type.__dict__['__mro__']       .__get__,
                    TP_DICTOFFSET = type.__dict__['__dictoffset__'].__get__,
                    TP_DICT       = type.__dict__['__dict__']      .__get__,
                    TP_GETATTR    = type.__getattribute__,
                    is_class      = type.__instancecheck__.__get__(type),
                    isinstance    = isinstance,
                    dtypes        = (type(int.real), type(complex.real)),
                    error         = AttributeError
                    ):
    fget = None
    fset = None
    res  = None
    tp   = Py_TYPE(ob)
    mro  = TP_MRO(tp)
    for base in mro:
        if 1:
            dict  = TP_DICT(base)
        if name in  dict:
            res   = dict[name]
            rtp   = Py_TYPE(res)
            
            try   : fget = TP_GETATTR(rtp, '__get__')
            except: break

            try   : fset = TP_GETATTR(rtp, '__set__')
            except: pass
            else  : return fget(res, ob, tp)

            try   : fset = TP_GETATTR(rtp, '__delete__')
            except: pass
            else  : return fget(res, ob, tp)
            break
        
    if not is_class(ob):
        if not TP_DICTOFFSET(tp):
            if fget is not None:
                return fget(res, ob, tp)
            raise error(name)
        for base in mro:
            dict = TP_DICT(base)
            if '__dict__' in dict:
                ob_dptr = dict['__dict__']
                if isinstance(ob_dptr, dtypes):
                    ob_dict = ob_dptr.__get__(ob, tp)
                    break
        else:
            raise SystemError("nonzero __dictoffset__ despite no __dict__")
    else:
        ob_dict = TP_DICT(ob)
    if name not in ob_dict:
        if fget is not None:
            return fget(res, ob, tp)
        raise error(name)
    return ob_dict[name]  
