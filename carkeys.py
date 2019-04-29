def join(sep, seq):
	seq = iter(seq)
	one = next(seq, seq)
	if one is seq: 
        return seq
	two = next(seq)
	if two is seq: 
      return [one].__iter__
	it = zip_longest(
        [(one, sep)], 
        zip(chain([two], seq)),
        fillvalue=(sep,))
	it = starmap(concat, it)
	return chained(it)
    
def mapping_pop(D, k, *d):
    try:
        d = D[k]
    except LookupError:
        if not d:
            raise
        [d] = d
        return d
    del D[k]
    return d

def startswith(seq, prefix, *subseq):
    '''The same as str.startswith except works with any two iterables

        >>> a = 'concurrent.futures.Executor'.split('.')
        >>> startswith(a, ('concurrent','futures'))
        True
        >>> startswith(a, ('futures',), 1)
        True
    '''
    if not prefix:
        return True
    if seq == prefix:
        return True
    if subseq:
        if len(subseq) == 1:
            [a] = subseq
            seq = islice(seq, a, None)
        else:
            seq = islice(seq, *subseq)
    for i, j in zip_longest(seq, prefix, fillvalue=nanny):
        if i != j:    return j is nanny
    return True

def sortmap(mp, key=None, reverse=False):
    try:
        pop = mp.pop
    except:
        def pop(k):
            v = mp[k]
            del mp[k]
            return v
    for k in sorted(mp, key=key, reverse=reverse): mp[k] = pop(k)

def summer(i, *j):
    if j: lo, [hi] = i, j
    else: lo,  hi  = 0, i
    j = (hi-1) * hi//2
    return (j-((lo-1)*lo//2)) if lo else j    if lo:
        return ( - ((lo-1) * lo//2)
    
    if not j:
        j = i
        i = 0
    
        if not j:
            return 0
        return (j-1) * j//2
