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
