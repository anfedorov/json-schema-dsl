"""
Scheemey is a JSON Schema DSL.

It parses a schema and uses it to verify and type-cast JSON objects like:

Creating `datetime.date` objects out of the value of strings or ints,
and a `namedtuple`'s out of lists of constant length.

Doctests:
  >>> parse('''{
  ...     'foo': [isodate, ...],
  ...     'bar': {
  ...       payee: decimal,
  ...       ...
  ...     },
  ...     'baz': Player(name:str, score:int),
  ...   }''',
  ...   {
  ...     'foo': ['2014-01-01', '2014-02-01'],
  ...     'bar': {
  ...       'p1': 3,
  ...       'p2': 2,
  ...       'p3': 1,
  ...     },
  ...     'baz': ['bob', 10],
  ...   }
  ... )
  {'bar': {'p2': Decimal('2'), 'p3': Decimal('1'), 'p1': Decimal('3')}, 'foo': [datetime.date(2014, 1, 1), datetime.date(2014, 2, 1)], 'baz': Player(name='bob', score=10)}

"""

import re

from collections import namedtuple
from decimal import Decimal
from dateutil import parser
from functools import partial

token_parsers = {
  'decimal': Decimal,
  'payee': str,
  'str': str,
  'float': float,
  'int': int,
  'isodate': lambda x: parser.parse(x).date(),
  'any': lambda x: x,
}

def parse(schema, x=None):
  """Parses a schema and object.

  Arguments:
    schema (str): representing a JSON schema definition
    x (object): representing a JSON object

  Doctests:

    >>> parse('isodate', '2014-01-01')
    datetime.date(2014, 1, 1)

    >>> parse('[isodate, ...]', ['2014-01-01', '2014-02-01'])
    [datetime.date(2014, 1, 1), datetime.date(2014, 2, 1)]

    >>> parse('{payee: decimal, ...}', {'one': 1, 'two': 2})
    {'two': Decimal('2'), 'one': Decimal('1')}

    >>> parse('(str, str)', ('foo', 'bar'))
    ('foo', 'bar')

    >>> parse('Point(x:float, y:float)', (1, 2))
    Point(x=1.0, y=2.0)

  """
  if x is None:
    return partial(parse, schema)

  schema = schema.strip()

  if schema == '':
    return None

  if schema in token_parsers:
    return token_parsers[schema](x)

  if schema.startswith('{') and schema.endswith('}'):  # is dict
    m = re.match(r'^{\s*(.+)\s*:\s*(.+)\s*,\s*\.\.\.\s*}$', schema)
    if m:  # is repeating
      assert isinstance(x, dict), 'not dict: %s' % x
      return {parse(m.group(1), k): parse(m.group(2), v) for k, v in x.items()}

    else:  # is specific
      return parse_object(schema[1:-1], x)

  if schema.startswith('[') and schema.endswith(']'):  # is list
    m = re.match(r'^\[(.*),\s*\.\.\.\s*\]$', schema)
    if m:  # is repeating
      assert isinstance(x, list), 'not list: %s' % x
      return [parse(m.group(1), v) for v in x]

    else:  # is optional
      assert False, 'list schema must end in ", ..."'

  if schema.startswith('(') and schema.endswith(')'):  # is tuple
    schema_parts = schema[1:-1].split(',')
    assert len(schema_parts) == len(x), 'bad number of parts: %s' % x
    return tuple(parse(s, v) for s, v in zip(schema_parts, x))

  m = re.match(r'^(\w+)\((.*)\)$', schema)  # is namedtuple
  if m:
    param = namedtuple('param', ['name', 'type'])
    params = [param(*p.split(':')) for p in m.group(2).split(',')]
    assert len(params) == len(x), 'bad len: %s' % x
    nt = namedtuple(m.group(1), [p.name.strip() for p in params])
    return nt(*[parse(p.type.strip(), v) for p, v in zip(params, x)])

  assert False, 'what is this i dont even: "%s"' % schema


def find_closing(string, open_index):
  open_char = string[open_index]
  assert open_char in '{(['
  close_char = '}' if open_char == '{' else \
               ')' if open_char == '(' else \
               ']'
  depth = 1
  index = open_index + 1
  while depth > 0:
    if string[index] == open_char:
      depth += 1
    elif string[index] == close_char:
      depth -= 1
    index += 1
  return index

def verify_balanced(s):
  """Verifies that all {[( characters have closing partners.

  Returns:
    the index of an out of first unbalanced character or `None`

  Doctests:
    >>> verify_balanced('asdf (foo) [bar] [[baz], {}, ()]')
    None

    >>> verify_balanced('asdf (foo [bar] [[baz], {}, ()]')
    5

  """
  opening = '{[('
  closing = '}])'
  stack = []

  for i, c in enumerate(s):
    if c in opening:
      stack.append((i, opening.index(c)))
    elif c in closing:
      j, x = stack.pop()
      if x != closing.index(c):
        return j

  if len(stack) > 0:
    j, x = stack.pop()
    return j

  return None



def find_comma(string, index):
  while string[index] != ',':
    if string[index] in '{([':
      index = find_closing(string, index)
    else:
      index += 1
  return index

def parse_object(schema, o):
  schema = schema.strip()

  if not schema:
    return {}

  retval = {}  
  m = re.match(r'^(\'([^\']+)\':\s*)(.*?),', schema, flags=re.S) or re.match(r'^"([^"]+)":\s*(.)', schema)
  assert m, 'bad literal object: %s' % schema

  key = m.group(2)
  assert key in o, 'key %s not found in %s' % (key, o)

  value_start = len(m.group(1))
  if schema[value_start] in '([{':
    value_end = find_closing(schema, value_start)
    retval[key] = parse(schema[value_start:value_end], o[key])

  else:
    value_end = find_comma(schema, value_start)
    retval[key] = parse(schema[value_start:value_end], o[key])

  retval.update(parse_object(schema[value_end+1:], o))

  return retval
