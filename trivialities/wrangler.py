import re
# I've probably spent *hours* trying to come up with a pattern that even works
# to detect whether Python will mangle a name. Apparently, the key to understanding
# negative lookbehind assertions is to stay awake for 27 hours...

pat = re.compile('\A'
                 '__'
                 '[0-9A-Za-z]'
                 '[0-9A-Za-z_]*'
                 '(?<!__)'
                 '\Z')
