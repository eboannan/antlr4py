"""ANTLR character escapes and versioned Unicode 15.0 general categories."""
import json
import re
from functools import lru_cache
from pathlib import Path

from antlr4.IntervalSet import IntervalSet
from .errors import GrammarError


def character(text, index):
    char = text[index]
    if char != '\\':
        return ord(char), index + 1
    index += 1
    if index >= len(text):
        raise GrammarError('Unterminated character escape')
    char = text[index]
    escapes = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
               '\\': '\\', "'": "'", '"': '"', ']': ']', '-': '-'}
    if char in escapes:
        return ord(escapes[char]), index + 1
    if char == 'u':
        start = index + 1
        if start < len(text) and text[start] == '{':
            end = text.find('}', start)
            if end < 0:
                raise GrammarError('Unterminated Unicode escape')
            digits, next_index = text[start+1:end], end+1
        else:
            digits, next_index = text[start:start+4], start+4
            if len(digits) != 4:
                raise GrammarError('Unicode escape requires four hex digits')
        if not digits or any(c not in '0123456789abcdefABCDEF' for c in digits):
            raise GrammarError('Invalid Unicode escape')
        value = int(digits, 16)
        if value > 0x10FFFF:
            raise GrammarError('Unicode escape exceeds U+10FFFF')
        return value, next_index
    raise GrammarError(f'Unsupported escape: \\{char}')


def literal(text):
    body, chars, index = text[1:-1], [], 0
    while index < len(body):
        value, index = character(body, index)
        chars.append(value)
    # ANTLR treats adjacent UTF-16 surrogate escapes as a single code point.
    result, index = [], 0
    while index < len(chars):
        value = chars[index]
        if 0xD800 <= value <= 0xDBFF and index+1 < len(chars) and 0xDC00 <= chars[index+1] <= 0xDFFF:
            value = 0x10000 + ((value-0xD800) << 10) + chars[index+1]-0xDC00
            index += 1
        result.append(chr(value))
        index += 1
    return ''.join(result)


@lru_cache(maxsize=1)
def unicode_categories():
    return json.loads(Path(__file__).with_name('unicode15.json').read_text())['categories']


@lru_cache(maxsize=1)
def unicode_properties():
    data = json.loads(Path(__file__).with_name('unicode_properties.json').read_text())
    normalize = lambda name: re.sub(r'[ _-]', '', name).casefold()
    data['properties'] = {normalize(k): v for k, v in data['properties'].items()}
    data['aliases'] = {normalize(k): normalize(v) for k, v in data['aliases'].items()}
    return data


def property_set(name):
    data = unicode_properties()
    key = re.sub(r'[ _-]', '', name).casefold()
    key = data['aliases'].get(key, key)
    if key in data['properties']:
        result = IntervalSet()
        for start, stop in data['properties'][key]:
            result.addRange(range(start, stop+1))
        return result
    aliases = {'Letter': 'L', 'Uppercase_Letter': 'Lu', 'Lowercase_Letter': 'Ll',
               'Titlecase_Letter': 'Lt', 'Modifier_Letter': 'Lm', 'Other_Letter': 'Lo',
               'Mark': 'M', 'Number': 'N', 'Decimal_Number': 'Nd', 'Punctuation': 'P',
               'Symbol': 'S', 'Separator': 'Z', 'Other': 'C', 'Unassigned': 'Cn'}
    aliases.update(dict(zip(
        ['Nonspacing_Mark', 'Spacing_Mark', 'Enclosing_Mark', 'Letter_Number', 'Other_Number',
         'Connector_Punctuation', 'Dash_Punctuation', 'Open_Punctuation', 'Close_Punctuation',
         'Initial_Punctuation', 'Final_Punctuation', 'Other_Punctuation', 'Math_Symbol',
         'Currency_Symbol', 'Modifier_Symbol', 'Other_Symbol', 'Space_Separator',
         'Line_Separator', 'Paragraph_Separator', 'Control', 'Format', 'Surrogate', 'Private_Use'],
        ['Mn', 'Mc', 'Me', 'Nl', 'No', 'Pc', 'Pd', 'Ps', 'Pe', 'Pi', 'Pf', 'Po',
         'Sm', 'Sc', 'Sk', 'So', 'Zs', 'Zl', 'Zp', 'Cc', 'Cf', 'Cs', 'Co'])))
    normalize = lambda value: re.sub(r'[ _-]', '', value).casefold()
    if '=' in name:
        key, name = name.split('=', 1)
        if normalize(key) not in ('gc', 'generalcategory'):
            raise GrammarError(f'Unsupported Unicode property: {key}')
    categories = unicode_categories()
    aliases.update({key: key for key in list(categories) + list('LMNPSZC')})
    name = {normalize(key): value for key, value in aliases.items()}.get(normalize(name), name)
    keys = [k for k in categories if k == name or len(name) == 1 and k.startswith(name)]
    if not keys:
        raise GrammarError(f'Unsupported Unicode general category: {name}')
    result = IntervalSet()
    for key in keys:
        for start, stop in categories[key]:
            result.addRange(range(start, stop+1))
    return result


def case_set(values):
    """ANTLR's simple upper/lower mapping; never expand multi-codepoint folds."""
    result = IntervalSet()
    result.addSet(values)
    for source, targets in unicode_properties()['case_mappings'].items():
        if int(source) in values:
            for target in targets:
                result.addOne(target)
    return result


def character_set(text):
    body, result, index = text[1:-1], IntervalSet(), 0
    if not body:
        raise GrammarError('Empty character set')
    while index < len(body):
        if body[index:index+3] in ('\\p{', '\\P{'):
            end = body.find('}', index+3)
            if end < 0:
                raise GrammarError('Unterminated Unicode property')
            values = property_set(body[index+3:end])
            if body[index+1] == 'P':
                values = values.complement(0, 0x10FFFF)
            result.addSet(values)
            index = end+1
            if index < len(body)-1 and body[index] == '-':
                raise GrammarError('Unicode properties cannot be range endpoints')
            continue
        start, after = character(body, index)
        if after < len(body)-1 and body[after] == '-':
            if body[after+1:after+4] in ('\\p{', '\\P{'):
                raise GrammarError('Unicode properties cannot be range endpoints')
            end, after = character(body, after+1)
            if end < start:
                raise GrammarError('Reversed character range')
            result.addRange(range(start, end+1))
        else:
            result.addOne(start)
        index = after
    return result


def negated_set(node):
    kind, value = node
    if kind == 'set':
        return character_set(value)
    if kind == 'range':
        result = IntervalSet()
        result.addRange(range(value[0], value[1]+1))
        return result
    if kind == 'lit' and len(value) == 1:
        result = IntervalSet()
        result.addOne(ord(value))
        return result
    if kind in ('seq', 'alt'):
        if kind == 'seq' and len(value) != 1:
            raise GrammarError('Negated sets require single-character alternatives')
        result = IntervalSet()
        for child in value:
            result.addSet(negated_set(child))
        return result
    raise GrammarError('Negated sets require character literals, ranges, or sets')
