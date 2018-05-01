"""Reindent

Modify aesthetic properties of source code like indentation

NOTE: String literals MUST BE r'raw' strings, or have any of the
chaacters prefixed with a backslash, prefixed with a backslash.
For example:
Indenter("b'abc\x00'") will generate a syntax error, and
Indenter("b'abc\\x00'") or Indenter(r"b'abc\x00') will not


OTHER NOTE: Not done many tests with this so can make no claims of its
reliability. It was able to reindent all .py modules in the 3.6 standard
library, but that isn't really testing.

The reindenter is only sophisitcated enought to deal with syntactically
important whitespace. Extraneous whitespace used in multiline tuple
literals, for example, must be realigned manually.

>>> code = '''
# a "coΜment" with a string - this source uses tabs for indentation
def hello():
	a=1;b=2
	print('Hello ωorld!')
'''
>>> self=CodeEditor(code, encoding='utf-8') # source contains unicode
                                            # and default encoding on windows
                                            # wont work see DEFAULT_ENCODING
                                            # which by default is equal to
                                            # locale.getpreferredencoding(False)
>>> self.indent_char = ' '
>>> print(self)

# a "coΜment" with a string
def hello():
    a=1;b=2
    print('Hello ωorld!')

>>> self.split_semicolons()
>>> self.indentation = 1
>>> print(self)

# a "coΜment" with a string
def hello():
 a=1
 b=2
 print('Hello ωorld!')
"""

import re
import pathlib
import io
import ast
import keyword
import locale
import codecs

from publicize import public, public_constants

DEFAULT_ENCODING = locale.getpreferredencoding(False)
KWS = frozenset(keyword.kwlist)
tqstrings = re.compile('''
(?P<v>(?P<prefix>(?:r|u|f|rf|fr|b|rb|br)?)
 \"\"\".*?\"\"\"
|\'\'\'.*?\'\'\')''', re.X|re.I|re.S)
sqstrings = re.compile(
    '(?P<v>(?P<prefix>(?:r|u|f|rf|fr|b|rb|br)?)(?P<q>[\'\"]).*?(?P=q))', re.I)
backslashes = re.compile('(?P<v>\\\\+(?=[\'\"]))')
comments = re.compile('(?P<v>#+.*)')
expressions = re.compile(
    "(?P<v>\([^\)]*?[^\(]*\)|\[[^\]]*?[^\[]*\]|\{[^\}]*?[^\{]*\})", re.S)
whitespace = re.compile('(?P<v>^[ \t]*)')
semicolons = re.compile('\n?(?P<indent>[ \t]*)(?P<a>.*);(?P<b>.*)')

class EncodingError(Exception):
    pass

@public
class CodeEditor:

    __slots__ = ('_original', '_comment_fields', '_sqstring_fields',
                 '_expression_fields', '_abstract', '_indentation',
                 '_indent_char', 'filename', '_backslash_fields',
                 '_tqstring_fields', '_encoding', '_cached',)

    def __init__(self, text, filename=None, encoding=DEFAULT_ENCODING):
        try:
            ast.parse(text)
        except IndentationError:
            pass
        codec = codecs.lookup(encoding)
        self._encoding = codec.name
        self._cached = None
        self._original = self._abstract = text
        self._strip()
        text = self._stripped
        lines = text.split('\n')
        pads = set()
        add = pads.add
        for line in lines:
            add(whitespace.search(line)['v'])
        chars = set(''.join(pads))
        if len(chars) > 1:
            raise SyntaxError('mixed tabs and spaces')
        elif len(chars):
            self._indent_char = chars.pop()
        else:
            self._indent_char = ' '
        lengths = sorted(map(len, pads))
        if len(lengths) > 1:
            self._indentation = lengths[1]
        else:
            self._indentation = lengths[0] if lengths[0] else 4
        self.filename = filename

    def __str__(self, *args, **kwargs):
        if self._cached is not None:
            return self._cached
        self._cached = self._apply()
        return self._cached

    def __bytes__(self):
        return bytes(str(self), self.encoding)

    def _apply(self):
        '''Get modified source code'''
        text = self._abstract
        for i, q in enumerate(self._expression_fields):
            text = text.replace(f'<expression {i}>', q, 1)
        for i, q in enumerate(self._comment_fields):
            text = text.replace(f'<comment {i}>', q, 1)
        for i, q in enumerate(self._sqstring_fields):
            text = text.replace(f'<sqstring {i}>', q, 1)
        for i, q in enumerate(self._tqstring_fields):
            text = text.replace(f'<tqstring {i}>' ,q, 1 )
        for i, q in enumerate(self._backslash_fields):
            text = text.replace(f'<backslash {i}>', q, 1)
        return text

    def __len__(self):
        return len(str(self))

    def _strip(self):
        text = self._original
        self._backslash_fields = []
        self._comment_fields = []
        self._tqstring_fields = []
        self._sqstring_fields = []
        self._expression_fields = []
        add_backslash_field = self._backslash_fields.append
        add_comment_field = self._comment_fields.append
        add_tqstring_field = self._tqstring_fields.append
        add_sqstring_field = self._sqstring_fields.append
        add_expression_field = self._expression_fields.append
        for i, q in enumerate(backslashes.finditer(text)):
            text = text.replace(q['v'], f'<backslash {i}>', 1)
            add_backslash_field(q['v'])
        for i, q in enumerate(tqstrings.finditer(text)):
            text = text.replace(q['v'], f'<tqstring {i}>', 1)
            add_tqstring_field(q['v'])
        for i, q in enumerate(sqstrings.finditer(text)):
            text = text.replace(q['v'], f'<sqstring {i}>', 1)
            add_sqstring_field(q['v'])
        for i, q in enumerate(comments.finditer(text)):
            text = text.replace(q['v'], f'<comment {i}>', 1)
            add_comment_field(q['v'])
        for i, q in enumerate(expressions.finditer(text)):
            text = text.replace(q['v'], f'<expression {i}>', 1)
            add_expression_field(q['v'])
        self._abstract = text
        self._stripped = text

    def get_identifiers(self):
        text = self._stripped
        text = field_prog.sub('', text)
        lits = set(re.findall(r'\b[.\w]+', text)) - KWS
        return {lit for lit in lits if not num_prog.search(lit)}

    @property
    def _stripped(self):
        return self._abstract
    @_stripped.setter
    def _stripped(self, value):
        self._abstract = value
        self._cached = None
        return self._abstract

    @property
    def encoding(self):
        return self._encoding

    @property
    def codec(self):
        return codecs.lookup(self._encoding)

    @encoding.setter
    def encoding(self, encoding):
        codec = codecs.lookup(encoding)
        text = str(self)
        bits, *_ = codec.encode(text)
        decoded = codec.decode(bits)
        if text != decoded:
            raise EncodingError(f'encoding text with {encoding!r} failed')
        self._encoding = encoding

    @property
    def size(self):
        '''Size of source in bytes'''
        return len(str(self).encode())

    @property
    def num_lines(self):
        '''Lines of code'''
        return 1 + str(self).count('\n')

    @property
    def indentation(self):
        '''Current indentation amount (if using spaces)'''
        return self._indentation
    @indentation.setter
    def indentation(self, value):
        if self.indent_char != ' ':
            raise ValueError('can only change indentation amount if the indent char is " "')
        if value == self.indentation:
            return
        old_pad = self.indent_char * self.indentation
        new_pad = ' '*value
        lines = self._stripped.split('\n')
        new = []
        add = new.append
        for line in lines:
            length = len(whitespace.match(line)['v'])
            if length:
                n = length // self.indentation
                line = line.replace(old_pad * n, new_pad*n, 1)
            add(line)
        self._stripped = '\n'.join(new)
        self._original = str(self)
        self._indentation = value

    @property
    def indent_char(self):
        return self._indent_char
    @indent_char.setter
    def indent_char(self, value):
        if value == self._indent_char:
            return
        new = []
        add = new.append
        lines = self._stripped.split('\n')
        if value == '\t' and self._indent_char == ' ':
            indentation = 1
            old_indent = self.indentation
            pad = ' '*old_indent
            for line in lines:
                length = len(whitespace.match(line)['v'])
                if length:
                    n = length // old_indent
                    line = line.replace(pad*n, '\t'*n, 1)
                add(line)
        elif value == ' ' and self._indent_char == '\t':
            indentation = 4
            pad = ' '*4
            for line in lines:
                length = len(whitespace.match(line)['v'])
                if length:
                    line = line.replace(length*'\t', pad*length, 1)
                add(line)
        else:
            raise ValueError('can only set indent char to a space or tab')
        self._indentation = indentation
        self._stripped = '\n'.join(new)
        self._original = str(self)
        self._indent_char = value

    def split_semicolons(self):
        '''Not really sure if works...'''
        text = self._stripped
        for q in semicolons.finditer(text):
            pad, a, b = q.groups()
            old = q.group()
            new = old.replace(';', f'\n{pad}')
            text = text.replace(old, new, 1)
        self._stripped = text

    def tabify(self):
        '''Same as self.indent_char = "\\t"'''
        self.indent_char = '\t'

    def untabify(self):
        '''Same as self.indent_char = " "'''
        self.indent_char = ' '

    def reindent(self, char=' ', n=1):
        '''Same as self.indent_char=char;self.indentation=n'''
        if char == ' ':
            self.indent_char = char
            self.indentation = n
        elif char == '\t':
            self.indent_char = char
        else:
            raise ValueError('char must be " " or "\t"')

    def indent(self, steps):
        '''Add extra indentation to the left'''
        if not steps:
            return
        lines = self._stripped.split('\n')
        pad = self.indentation * self.indent_char
        new = []
        add = new.append
        for line in lines:
            add(pad*steps+line)
        self._stripped = '\n'.join(new)
        self._original = str(self)

    def dedent(self, steps):
        '''Removes `steps` indentation from the left'''
        if not steps:
            return
        pat = re.compile(f'^{self.indent_char * self.indentation}')
        new = []
        add = new.append
        lines = self._stripped.split('\n')
        for line in lines:
            line = pat.sub('', line, steps)
            add(line)
        self._stripped = '\n'.join(new)
        self._original = str(self)

    def align_left(self):
        '''Recursively `dedent` until at least one line begins at col 1'''
        pat = re.compile(f'^{self.indent_char * self.indentation}')
        lines = self._stripped.split('\n')
        empty = True
        for line in lines:
            if not line:
                continue
            empty = False
            if not pat.match(line):
                break
        else:
            if not empty:
                self.dedent(1)
                self.align_left()

    def write(self, file):
        '''Write contents of `self` to `file.'''
        if hasattr(file, 'write'):
            file.write(str(self))
        else:
            with open(file, 'w') as fp:
                fp.write(str(self))

    @classmethod
    def from_file(cls, file, encoding=DEFAULT_ENCODING):
        '''Load source from filename or buffer'''
        try:
            if hasattr(file, 'read'):
                text = file.read()
                self = cls(file.read(), getattr(file, 'name', None))
                try:
                    file.close()
                finally:
                    return self
            else:
                with open(file) as fp:
                    return cls(fp.read(), getattr(fp, 'name', None))
        except SyntaxError as e:
            error = SyntaxError(f'{e.args[0]!r} in {file!r}', e.args[1])
            raise error from None

    def rstrip(self):
        '''Remove all extraneous trailing whitespace

           Whitespace in multiline strings is not extraneous are ignored'''
        text = self._original
        coms = []
        strs = []
        exps = []
        coms_append = coms.append
        strs_append = strs.append
        exps_append = exps.append
        trailing_space_sub = trailing_space.sub
        for i, q in enumerate(comments.finditer(text)):
            text = text.replace(q['v'], f'<comment {i}>', 1)
            coms_append(trailing_space_sub('', q['v']))
        for i, q in enumerate(strings.finditer(text)):
            text = text.replace(q['v'], f'<string {i}>', 1)
            strs_append(q['v'])
        lines = []
        lines_append = lines.append
        for line in text.split('\n'):
            lines_append(trailing_space_sub('', line))
        text = '\n'.join(lines)
        for i, q in enumerate(expressions.finditer(text)):
            text = text.replace(q['v'], f'<expression {i}>', 1)
            exps_append(q['v'])
        self._stripped = text
        self._comment_fields = coms
        self._string_fields = strs
        self._expression_fields = exps
        self._original = str(self)

    def asbytes(self):
        '''Encode `self` using currently set encoding'''
        return bytes(self)

    def __repr__(self):
        args = []
        if getattr(self, 'filename', None):
            args += [('filename', self.filename)]
        args += [('indentation', self.indentation),
                 ('indent_char', self.indent_char),
                 ('size', self.size),
                 ('num_lines', self.num_lines),
                 ('encoding', self.encoding)]
        args = ' '.join(f'{k}={v!r}' for k, v in args)
        return f'<{type(self).__qualname__} {args}>'

public_constants(Indenter = CodeEditor)
