"""Rule declarations, labels, and the expression subset for rule arguments."""
import ast
import re
from antlr4 import ParserRuleContext
from .errors import GrammarError
from .naming import escaped


def split_items(text):
    result, start, depth, quote, escaped = [], 0, 0, None, False
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char in '([{':
            depth += 1
        elif char in ')]}':
            depth -= 1
        elif char == ',' and depth == 0:
            result.append(text[start:index].strip())
            start = index+1
    if quote or depth:
        raise GrammarError('Unbalanced rule attribute/argument declaration')
    if text[start:].strip():
        result.append(text[start:].strip())
    return result


def declarations(text, *, literal_defaults=False):
    result = []
    for item in split_items(text):
        try:
            match = re.match(r'([A-Za-z_][A-Za-z_0-9]*)', item)
            if match is None:
                raise ValueError()
            name = match[1]
            parsed = ast.parse('def f('+escaped(name)+item[len(name):]+'):\n pass').body[0].args
            if len(parsed.args) != 1 or parsed.vararg or parsed.kwarg or parsed.kwonlyargs or parsed.posonlyargs:
                raise ValueError()
            default = None
            if parsed.defaults:
                default = (repr(ast.literal_eval(parsed.defaults[0])) if literal_defaults else
                           ast.unparse(parsed.defaults[0]))
        except (SyntaxError, ValueError, TypeError) as exc:
            raise GrammarError('Rule declarations require Python-style names/types and valid initializers; argument defaults must be literals') from exc
        result.append((name, default))
    return result


def alt_parts(node):
    label, assoc = None, None
    while node[0] in ('altlabel', 'assoc'):
        if node[0] == 'altlabel':
            label, node = node[1]
        else:
            assoc, node = node[1]
    return label, assoc, node


def element(node):
    while node[0] == 'label':
        node = node[1][2]
    return node


def prepare(grammar):
    from .grammar import walk
    global_labels = {}
    for rule in grammar.rules:
        grammar.attributes.setdefault(rule, {'args': [], 'returns': [], 'locals': []})
    for rule, node in grammar.rules.items():
        attrs = grammar.attributes.get(rule, {'args': [], 'returns': [], 'locals': []})
        grammar.attributes[rule] = attrs
        names = [name for group in attrs.values() for name, _ in group]
        default_seen = False
        for _, default in attrs['args']:
            if default is None and default_seen:
                raise GrammarError('Required rule arguments must precede defaults')
            default_seen |= default is not None
        if len(set(names)) != len(names):
            raise GrammarError(f'Duplicate rule attribute in {rule}')
        label_types = {}
        for kind, value in walk(node):
            if kind != 'label':
                continue
            name, many, child = value
            target = element(child)
            if target[0] in ('ref', 'invoke'):
                reference = target[1][0] if target[0] == 'invoke' else target[1]
                signature = ('rule', reference, many) if reference in grammar.rules else ('token', many)
            elif target[0] in ('lit', 'wildcard', 'not') or token_block(target, grammar):
                signature = ('token', many)
            else:
                raise GrammarError('Labels require a token, token alternative, or rule reference')
            if name in label_types and label_types[name] != signature:
                raise GrammarError(f'Incompatible label definitions: {name}')
            label_types[name] = signature
        for name in names + list(label_types):
            if (name.startswith('_') or hasattr(ParserRuleContext, escaped(name))
                    or name in {'parser', 'start', 'stop', 'exception', 'children', 'ruleIndex'}
                    or name in {'self', 'parent', 'invokingState'}
                    or name in grammar.rules or name in grammar.tokens):
                raise GrammarError(f'Attribute/label conflicts with a grammar or runtime name: {name}')
        if set(names) & set(label_types):
            raise GrammarError(f'Label conflicts with rule attribute in {rule}')
        if len({escaped(name) for name in names+list(label_types)}) != len(names)+len(label_types):
            raise GrammarError(f'Rule attributes collide after Python escaping in {rule}')
        outer = node[1] if node[0] == 'alt' else [node]
        labels = [alt_parts(alt)[0] for alt in outer]
        if any(labels) and not all(labels):
            raise GrammarError(f'All alternatives in {rule} must be labeled, or none')
        for label, alt in zip(labels, outer):
            if any(k == 'altlabel' for k, _ in walk(alt_parts(alt)[2])):
                raise GrammarError('Alternative labels must be on outermost alternatives')
            if label:
                if label.casefold() in {r.casefold() for r in grammar.rules}:
                    raise GrammarError(f'Alternative label conflicts with rule name: {label}')
                if label in global_labels and global_labels[label] != rule:
                    raise GrammarError(f'Alternative label is shared by different rules: {label}')
                global_labels[label] = rule
        for kind, value in walk(node):
            if kind not in ('ref', 'invoke'):
                continue
            target, arguments = value if kind == 'invoke' else (value, [])
            if target not in grammar.rules:
                if kind == 'invoke':
                    raise GrammarError('Only parser rules accept arguments')
                continue
            target_args = grammar.attributes.get(target, {}).get('args', [])
            minimum = sum(default is None for _, default in target_args)
            if not minimum <= len(arguments) <= len(target_args):
                raise GrammarError(f'Wrong number of arguments for rule {target}')


def token_block(node, grammar):
    kind, value = node
    if kind == 'ref':
        return value in grammar.tokens or value == 'EOF'
    if kind == 'lit':
        return True
    if kind == 'seq':
        return len(value) == 1 and token_block(value[0], grammar)
    if kind == 'alt':
        return all(token_block(child, grammar) for child in value)
    return False
