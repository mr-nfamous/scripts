
from collections import *
from itertools import *

chain_from_iterable = chain.from_iterable

def slicer(sq, k, a=None, b=None):
    '''Chop up a (sub)sequence into `k-sized` chunks

    `a` and `b` are optional arguments denoting the start and stop
    index of a subsequence of sq. Since only positive strides are valid
    the ordering of `a` and `b` doesn't matter. Whichever is highest
    be the "stop", and the subsequence will contain every element
    from sq[a] to sq[b-1].
    '''
    if k < 1:
        raise ValueError("zero/negative stride")
    return [sq[i:i+k] for i in range(len(sq))[slice(a,b,k)]]

class ChainSeq(Sequence):

    __slots__ = '__groups', '__items'

    def __add__(me, it):

        if not sequence_check(it):
            return NotImplemented

        if chainseq_check(it):
            it = [*it.__groups]
        else:
            it = [*it]

        items = islice(accumulate(map(len, [me, *it])), 1, None)
        self = new_object(type(me))
        self.__items = [*me.__items, *items]
        self.__groups = [*me.__groups] + it
        return self

    def __contains__(self, item):
        return any(i==item for i in chain_from_iterable(self.__groups))

    def __eq__(me, it):
        if it is me:
            return True
        if not chainseq_check(it):
            return NotImplemented
        return it.__groups == me.__groups

    def __getitem__(self, i):
        if slice_check(i):
            return [*self][i]
        size = len(self)
        if i < 0:
            i = size + i
        if i < 0 or i >= size:
            raise IndexError('slot index out of range')
        k = bisect(self.__items, i) - 1
        j = self.__items[k]
        return self.__groups[k][i-j]

    def __init__(self, *seqs):
        self.__items = [0, *accumulate(map(len, seqs))]
        self.__groups = [*seqs]

    def __iter__(self):
        return chain_from_iterable(self.__groups)

    def __len__(self):
        return self.__items[-1]

    def __mul__(me, n):
        n = index(n)
        self = new_object(type(me))

        if n < 2:
            if n:
                self.__groups = me.__groups.copy()
                self.__items = me.__items.copy()
            else:
                self.__groups, self.__items = [], []
            return self

        *a, b = me._ChainSeq__items
        g = me.__groups
        c = [b, *((n-1) * [*map(len, g)])]
        self.__items = [*a, *accumulate(c)]
        self.__groups = g * n
        return self

    def __repr__(self):
        return f'{type(self).__name__}{*self.__groups,!r}'

    def __reversed__(self):
        return chain_from_iterable(map(reversed, reversed(self.__groups)))

    def __set_name__(self, cls, var):
        pass

    def count(self, value):
        return countOf(chain_from_iterable(self.__groups), value)

    def index(self, x, a=0, b=None):
        seq = chain_from_iterable(self.__groups)

        if not a:
            if b is None:
                return indexOf(seq, x)
            a = 0
        n = len(self)
        if b is None:
            b = n
        if a < 0:
            a = max(0, a + n)
        if b < 0:
            b = max(0, b + n)
        if b <= a:
            return -1

        return indexOf(islice(seq, a, b), x) + a

    def find(self, x, a=0, b=None):
        try:
            return self.index(x, a, b)
        except ValueError:
            return -1

    def rindex(self, x, a=0, b=None):
        r = self.rfind(x, a, b)
        if r == -1:
            raise ValueError("seq.rindex(x): x not in seq")
        return r

    def rfind(self, x, a=0, b=None):
        n = len(self)
        a, b, _ = slice(a, b).indices(n)
        if a >= b:
            return -1
        seq = [*self]
        rev = reversed(seq)
        par = islice(rev, n-b, n-a)
        res = next(dropwhile(abstract_ne(x), par), seq)
        if res is seq:
            return -1
        return rev.__length_hint__()

    @classmethod
    def from_nested(cls, *nested, depth=1):
        while depth > 0:
            depth -= 1
            nested = [group
                      for groups in nested
                      for group in groups]
        return cls(*nested)

    @classmethod
    def from_strings(cls, *strings):
        ''' Split on whitespace each argument to *strings

        ie.
        >>> ChainSeq.from_strings("ab cd", "ef gh")
        ChainSeq(["ab", "cd"], ["ef", "gh"])
        >>> _[2]
        'ef'

        '''
        return cls.from_nested(map(split_string, strings))

    @property
    def groups(self):
        return (*self.__groups,)

def _abstract_f(*funcs, prefix='abstract', sep='_'):
    '_abstract_f(eq) -> abstract_eq; filter(abstract_eq(2), range(5))'
    ns = globals()
    for f in funcs:
        name = f'{prefix}{sep}{f.__name__}'
        ns[name] =  MethodType(_type_call.__get__(MethodType), f)

import re
chainseq_check = ChainSeq.__instancecheck__
split_string = re.compile(r'\S+').findall
sequence_check = Sequence.__instancecheck__
from publicize import *
star_export('re', 'collections', 'itertools', 'operator', 'publicize', 'bisect')

from bisect import bisect_right as bisect
from operator import attrgetter as AG, methodcaller as MC, itemgetter as IG
from operator import *
from functools import partial as pt
from types import MethodType

_type_call = type.__call__
_fast_new = _type_call.__get__
_abstract_f(ne, eq, lt, le, ge, gt)
frozen              = frozenset((bytes, memoryview, range, str, tuple))
slice_check         = slice.__instancecheck__
new_object          = object.__new__
fast_slice          = _fast_new(slice)
chain_from_iterable = chain.from_iterable
first_item          = IG(0)
rorder = IG(slice(None, None, -1))

def test_indices(sq):
    global q
    q = 0
    self = ChainSeq(sq)
    this = ''.join(sq)
    n = len(this)
    indices= [None, *range(n)]
    find_this, find_self = this.find, self.find
    rfind_this, rfind_self = this.rfind, self.rfind
    for ch in set(this):
        for i, j in product(indices, repeat=2):
            L = find_this(ch, i, j)
            if L != -1:
                assert self.index(ch, i, j) == L
            assert L == find_self(ch, i, j)
            R = rfind_this(ch, i, j)
            if R != -1:
                assert self.rindex(ch, i, j) == R
            assert R == rfind_self(ch, i, j)
            q += 1
            
if __name__ == '__main__':
    test_indices(ChainSeq('ChainSeq', '123'))
    packed = ['a', 'bc', range(3)]
    unpacked = [a for b in packed for a in b]
    sq = ChainSeq(*packed)
    assert sq+sq == ChainSeq(*(packed*2))
    assert [*(sq*3)]==unpacked*3
    assert sq[:3] == [*'abc']
    assert [*sq] == unpacked
    assert len(sq) == len(unpacked)
    assert [*reversed(sq)]==unpacked[::-1]
    assert sq.count(1)==1 and sq.count('f')==0
    assert [*sq.from_nested([range(2)], [range(3)])] == [0,1,*range(3)]
    assert [*sq.from_strings('a b', 'cd ef')]==['a', 'b', 'cd', 'ef']
    assert [a for b in sq.groups for a in b] == unpacked
    assert sq.find(-1) is -1
    assert sq.find('a') is 0
    for item in unpacked:
        assert unpacked.index(item) == sq.index(item)
        for start in range(-len(unpacked), len(unpacked)):
            try:
                i = unpacked.index(item, start, None)
                assert sq.index(item, start) == i
            except: pass
    assert slicer(sq, 2) == [['a', 'b'], ['c', 0], [1, 2]]
