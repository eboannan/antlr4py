"""Grammar frontend and semantic validation for the Python-only generator."""
import re
import io
import tokenize
from copy import deepcopy
from dataclasses import dataclass, field

from .characters import literal, character_set
from .errors import GrammarError
from .annotations import declarations, split_items, alt_parts, element, prepare
from .naming import escaped


@dataclass
class LexerRule:
    name: str
    node: tuple
    mode: str = 'DEFAULT_MODE'
    fragment: bool = False
    token_type: int = 0
    case_insensitive: bool | None = None


@dataclass
class Source:
    name: str
    kind: str
    rules: dict
    lexer: list
    declared: list
    modes: list
    channels: dict
    imports: list
    token_vocab: str | None
    attributes: dict = field(default_factory=dict)
    named_actions: dict = field(default_factory=dict)
    rule_actions: dict = field(default_factory=dict)
    rule_catches: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)


@dataclass
class Grammar:
    name: str
    rules: dict
    lexer: list
    tokens: dict
    literals: dict
    left_recursive: set = field(default_factory=set)
    kind: str = 'combined'
    modes: list = field(default_factory=lambda: ['DEFAULT_MODE'])
    channels: dict = field(default_factory=lambda: {'DEFAULT_TOKEN_CHANNEL': 0, 'HIDDEN': 1})
    context_rules: dict = field(default_factory=dict)
    attributes: dict = field(default_factory=dict)
    named_actions: dict = field(default_factory=dict)
    rule_actions: dict = field(default_factory=dict)
    rule_catches: dict = field(default_factory=dict)
    code: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)


def action_block(text, pos):
    """Read balanced Python braces without treating strings/comments as grammar."""
    tail = text[pos:]
    lines = tail.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    depth = 0
    try:
        for token in tokenize.generate_tokens(io.StringIO(tail).readline):
            if token.type == tokenize.OP:
                depth += token.string == '{'
                depth -= token.string == '}'
                if depth == 0:
                    end = offsets[token.end[0]-1] + token.end[1]
                    return tail[:end]
    except (tokenize.TokenError, IndentationError) as exc:
        raise GrammarError('Unterminated or malformed Python action block') from exc
    raise GrammarError('Unterminated Python action block')


def scan(text):
    pattern = re.compile(
        r"\s+|//[^\n]*|/\*[\s\S]*?\*/|"
        r"'(?:\\.|[^'\\])*'|\[(?:\\.|[^\]\\])*\]|"
        r"[A-Za-z_][A-Za-z_0-9]*|[0-9]+|->|\+=|::|\.\.|[:;|()?*+<>=,{}~.@#\[\]]"
    )
    result, pos = [], 0
    while pos < len(text):
        if text[pos] == '{' and (not result or result[-1] not in ('options', 'tokens', 'channels')):
            block = action_block(text, pos)
            result.append(block)
            pos += len(block)
            continue
        if text[pos] == '[' and result:
            previous = result[-1]
            boundary = max((i for i, token in enumerate(result) if token == ';'), default=-1)
            header = ':' not in result[boundary+1:]
            argument = bool(re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', previous)) and (
                header or previous[0].islower())
            if previous in ('returns', 'locals') or argument:
                start, depth, quote, escaped = pos, 1, None, False
                pos += 1
                while pos < len(text) and depth:
                    char = text[pos]
                    if quote:
                        if escaped:
                            escaped = False
                        elif char == '\\':
                            escaped = True
                        elif char == quote:
                            quote = None
                    elif char in "'\"":
                        quote = char
                    elif char == '[':
                        depth += 1
                    elif char == ']':
                        depth -= 1
                    pos += 1
                if depth:
                    raise GrammarError('Unterminated rule attribute/argument list')
                result.append(text[start:pos])
                continue
        match = pattern.match(text, pos)
        if not match:
            line = text.count('\n', 0, pos) + 1
            raise GrammarError(f'Unsupported syntax at line {line}: {text[pos:pos+20]!r}')
        value = match.group()
        if not value.isspace() and not value.startswith(('//', '/*')):
            result.append(value)
        pos = match.end()
    return result


class Reader:
    def __init__(self, text):
        self.items = scan(text) + ['<end>']
        self.pos = 0

    def peek(self):
        return self.items[self.pos]

    def take(self, expected=None):
        value = self.peek()
        if expected is not None and value != expected:
            raise GrammarError(f'Expected {expected!r}, got {value!r}')
        if value == '<end>':
            raise GrammarError('Unexpected end of grammar')
        self.pos += 1
        return value

    def identifier(self):
        value = self.take()
        if not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', value):
            raise GrammarError(f'Invalid identifier: {value}')
        return value

    def options(self):
        self.take('options')
        self.take('{')
        options = {}
        while self.peek() != '}':
            name = self.identifier()
            self.take('=')
            values = []
            while self.peek() != ';':
                values.append(self.take())
            self.take(';')
            if name in options or not values:
                raise GrammarError(f'Duplicate or empty option: {name}')
            options[name] = literal(values[0]) if len(values) == 1 and values[0].startswith("'") else ''.join(values)
        self.take('}')
        return options

    def expression(self):
        alternatives = [self.alternative()]
        while self.peek() == '|':
            self.take()
            alternatives.append(self.alternative())
        return ('alt', alternatives) if len(alternatives) > 1 else alternatives[0]

    def alternative(self):
        assoc = None
        if self.peek() == '<':
            self.take('<'); self.take('assoc'); self.take('=')
            assoc = self.take()
            if assoc not in ('left', 'right'):
                raise GrammarError('assoc must be left or right')
            self.take('>')
        node = self.sequence()
        if self.peek() == '->':
            self.take()
            commands = []
            while True:
                name, argument = self.identifier(), None
                if self.peek() == '(':
                    self.take()
                    argument = self.take()
                    self.take(')')
                commands.append((name, argument))
                if self.peek() != ',':
                    break
                self.take()
            node = ('commands', (node, commands))
        node = ('assoc', (assoc, node)) if assoc else node
        if self.peek() == '#':
            self.take()
            node = ('altlabel', (self.identifier(), node))
        return node

    def bracket(self):
        text = self.take()
        if not text.startswith('['):
            raise GrammarError('Expected a bracketed attribute/argument list')
        return text[1:-1]

    def atom(self):
        value = self.take()
        if value.startswith('{'):
            if self.peek() == '?':
                self.take()
                return ('predicate', value[1:-1])
            return ('action', value[1:-1])
        if value == '(':
            if self.peek() == 'options':
                if self.options():
                    raise GrammarError('ANTLR 4 has no supported block options')
                self.take(':')
            elif self.peek() == ':':
                self.take()
            node = self.expression()
            self.take(')')
            return node
        if value == '~':
            return ('not', self.atom())
        if value == '.':
            return ('wildcard', None)
        if value.startswith("'"):
            text = literal(value)
            if not text:
                raise GrammarError('Empty literals are unsupported')
            if self.peek() == '..':
                self.take()
                end = literal(self.take())
                if len(text) != 1 or len(end) != 1 or ord(text) > ord(end):
                    raise GrammarError('Invalid character range')
                return ('range', (ord(text), ord(end)))
            return ('lit', text)
        if value.startswith('['):
            return ('set', value)
        if re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', value):
            if value[0].islower() and self.peek().startswith('['):
                return ('invoke', (value, split_items(self.bracket())))
            return ('ref', value)
        raise GrammarError(f'Unsupported expression element: {value!r}')

    def sequence(self):
        nodes = []
        while self.peek() not in ('|', ')', ';', '->', '#', '<end>'):
            label = None
            if (self.pos+1 < len(self.items) and
                    re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', self.peek()) and
                    self.items[self.pos+1] in ('=', '+=')):
                label = (self.take(), self.take() == '+=')
            node = self.atom()
            if self.peek() == '<':
                self.take()
                element_options = {}
                while True:
                    option = self.identifier()
                    self.take('=')
                    value = self.take()
                    if option in element_options:
                        raise GrammarError('Duplicate element option')
                    element_options[option] = value
                    if self.peek() != ',':
                        break
                    self.take()
                self.take('>')
                if set(element_options)-{'fail', 'p', 'tokenIndex'}:
                    raise GrammarError('Unsupported element option')
                if 'fail' in element_options:
                    if node[0] != 'predicate':
                        raise GrammarError('fail is valid only on semantic predicates')
                    node = ('fail', (node, element_options['fail']))
                if 'p' in element_options:
                    if node[0] != 'ref' or not node[1][0].islower() or not element_options['p'].isdigit():
                        raise GrammarError('p requires a parser-rule reference and nonnegative integer')
                    node = ('call', (node[1], int(element_options['p'])))
            if label:
                node = ('label', (*label, node))
            if self.peek() in ('?', '*', '+'):
                operator = self.take()
                if self.peek() == '?':
                    self.take()
                    operator += '?'
                node = (operator, node)
            nodes.append(node)
        return ('seq', nodes)


def walk(node):
    yield node
    kind, value = node
    if kind in ('alt', 'seq'):
        for child in value:
            yield from walk(child)
    elif kind in ('?', '*', '+', '??', '*?', '+?', 'not'):
        yield from walk(value)
    elif kind == 'assoc':
        yield from walk(value[1])
    elif kind == 'commands':
        yield from walk(value[0])
    elif kind == 'altlabel':
        yield from walk(value[1])
    elif kind == 'label':
        yield from walk(value[2])
    elif kind == 'fail':
        yield from walk(value[0])


def parse_grammar(text):
    reader = Reader(text)
    kind = reader.peek() if reader.peek() in ('lexer', 'parser') else 'combined'
    if kind != 'combined':
        reader.take()
    reader.take('grammar')
    name = reader.identifier()
    reader.take(';')
    rules, lexer, names, declared = {}, [], set(), []
    modes, channels = ['DEFAULT_MODE'], {'DEFAULT_TOKEN_CHANNEL': 0, 'HIDDEN': 1}
    mode = 'DEFAULT_MODE'
    imports, token_vocab = [], None
    named_actions, rule_actions, rule_catches = {}, {}, {}
    attributes, options = {}, {}
    while reader.peek() != '<end>':
        if reader.peek() == '@':
            reader.take()
            scope, action = None, reader.identifier()
            if reader.peek() == '::':
                reader.take()
                scope, action = action, reader.identifier()
            if scope not in (None, 'parser', 'lexer') or action not in ('header', 'members'):
                raise GrammarError('Named actions support parser/lexer header and members only')
            if lexer or rules:
                raise GrammarError('Grammar named actions must precede rules')
            block = reader.take()
            if not block.startswith('{'):
                raise GrammarError('Expected a Python action block')
            targets = [scope] if scope else (['parser', 'lexer'] if kind == 'combined' else [kind])
            for target in targets:
                if (target, action) in named_actions:
                    raise GrammarError(f'Duplicate named action: {target}::{action}')
                named_actions[target, action] = block[1:-1]
            continue
        if reader.peek() == 'import':
            if lexer or rules:
                raise GrammarError('Imports must precede rules')
            reader.take()
            while True:
                imported = reader.identifier()
                if reader.peek() == '=':
                    reader.take()
                    imported = reader.identifier()
                if imported in imports:
                    raise GrammarError(f'Duplicate import: {imported}')
                imports.append(imported)
                if reader.peek() != ',':
                    break
                reader.take()
            reader.take(';')
            continue
        if reader.peek() == 'options':
            if lexer or rules:
                raise GrammarError('Options must precede rules')
            parsed = reader.options()
            allowed = {'tokenVocab', 'language', 'caseInsensitive', 'superClass',
                       'contextSuperClass', 'TokenLabelType', 'accessLevel', 'exportMacro'}
            if set(parsed)-allowed or set(parsed) & set(options):
                raise GrammarError('Unknown or duplicate grammar option')
            options.update(parsed)
            token_vocab = options.get('tokenVocab')
            if 'caseInsensitive' in options and options['caseInsensitive'] not in ('true', 'false'):
                raise GrammarError('caseInsensitive requires true or false')
            for key in ('superClass', 'contextSuperClass', 'TokenLabelType', 'tokenVocab'):
                if key in options and not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*', options[key]):
                    raise GrammarError(f'Invalid {key} name')
            continue
        if reader.peek() in ('channels', 'tokens'):

            declaration = reader.take()
            if declaration == 'channels' and kind != 'lexer':
                raise GrammarError('Custom channels require a lexer grammar')
            if lexer or rules:
                raise GrammarError('tokens/channels declarations must precede rules')
            reader.take('{')
            while reader.peek() != '}':
                value = reader.identifier()
                if declaration == 'channels':
                    if value in channels:
                        raise GrammarError(f'Duplicate channel: {value}')
                    channels[value] = len(channels)
                else:
                    if value in declared or not value[0].isupper() or value == 'EOF':
                        raise GrammarError(f'Invalid or duplicate token declaration: {value}')
                    declared.append(value)
                if reader.peek() != ',':
                    break
                reader.take()
            reader.take('}')
            continue
        if reader.peek() == 'mode':
            reader.take()
            if kind != 'lexer':
                raise GrammarError('Modes require a standalone lexer grammar')
            mode = reader.identifier()
            if mode in modes:
                raise GrammarError(f'Duplicate mode: {mode}')
            modes.append(mode)
            reader.take(';')
            continue
        fragment = False
        while reader.peek() in ('fragment', 'public', 'private', 'protected'):
            fragment |= reader.take() == 'fragment'
        rule = reader.identifier()
        if rule in names or rule == 'EOF' or rule.startswith('T__'):
            raise GrammarError(f'Duplicate or reserved rule: {rule}')
        names.add(rule)
        attrs = {'args': [], 'returns': [], 'locals': []}
        if reader.peek().startswith('['):
            attrs['args'] = declarations(reader.bracket(), literal_defaults=True)
        if reader.peek() == 'returns':
            reader.take()
            attrs['returns'] = declarations(reader.bracket())
        if reader.peek() == 'throws':
            reader.take()
            while reader.peek() not in ('locals', 'options', '@', ':'):
                reader.take()  # Python does not emit a throws declaration.
        if reader.peek() == 'locals':
            reader.take()
            attrs['locals'] = declarations(reader.bracket())
        rule_options = reader.options() if reader.peek() == 'options' else {}
        if set(rule_options) - ({'caseInsensitive'} if rule[0].isupper() else set()):
            raise GrammarError('Unsupported rule option')
        case_insensitive = None
        if 'caseInsensitive' in rule_options:
            if rule_options['caseInsensitive'] not in ('true', 'false'):
                raise GrammarError('caseInsensitive requires true or false')
            case_insensitive = rule_options['caseInsensitive'] == 'true'
        if rule[0].isupper() and any(attrs.values()):
            raise GrammarError('Lexer rules cannot declare rule attributes')
        attributes[rule] = attrs
        hooks = {}
        while reader.peek() == '@':
            reader.take()
            hook = reader.identifier()
            block = reader.take()
            if hook not in ('init', 'after') or hook in hooks or not block.startswith('{'):
                raise GrammarError('Rule actions support one @init and @after each')
            if rule[0].isupper():
                raise GrammarError('Lexer rule init/after actions are unsupported')
            hooks[hook] = block[1:-1]
        rule_actions[rule] = hooks
        reader.take(':')
        node = reader.expression()
        reader.take(';')
        catches = []
        while reader.peek() == 'catch':
            reader.take()
            header = reader.bracket()
            block = reader.take()
            if rule[0].isupper() or not block.startswith('{'):
                raise GrammarError('catch clauses require a parser rule and Python action block')
            catches.append((header, block[1:-1]))
        if catches:
            rule_catches[rule] = catches
        if reader.peek() == 'finally':
            reader.take()
            block = reader.take()
            if rule[0].isupper() or not block.startswith('{'):
                raise GrammarError('finally clauses require a parser rule and Python action block')
            hooks['finally'] = block[1:-1]
        if rule[0].isupper():
            if kind == 'parser':
                raise GrammarError('Lexer rules are not allowed in parser grammars')
            lexer.append(LexerRule(rule, node, mode, fragment, case_insensitive=case_insensitive))
        else:
            if fragment or kind == 'lexer':
                raise GrammarError('Lexer rules and fragments must start with uppercase')
            if rule.startswith('_'):
                raise GrammarError(f'Unsupported Python rule name: {rule}')
            rules[rule] = node
    return Source(name, kind, rules, lexer, declared, modes, channels, imports, token_vocab,
                  attributes, named_actions, rule_actions, rule_catches, options)


def read_grammar(text):
    source = parse_grammar(text)
    if source.imports or source.token_vocab:
        raise GrammarError('Use generate() to resolve imports and tokenVocab from files')
    return compile_grammar(source)


def lexer_literal(node):
    """A single literal, optionally followed by an action or lexer commands."""
    kind, value = node
    if kind == 'commands':
        if any(command in ('type', 'more') for command, _ in value[1]):
            return None
        return lexer_literal(value[0])
    if kind == 'lit':
        return value
    if kind == 'seq' and value and value[0][0] == 'lit':
        if len(value) == 1 or len(value) == 2 and value[1][0] in ('action', 'predicate'):
            return value[0][1]
    return None


def compile_grammar(source, vocabulary=None):
    if source.options.get('language', 'Python3') != 'Python3':
        raise GrammarError('Only language=Python3 is supported')
    name, kind, rules, lexer = source.name, source.kind, source.rules, source.lexer
    declared, modes, channels = source.declared, source.modes, source.channels
    if kind != 'lexer' and not rules:
        raise GrammarError('At least one parser rule is required')
    from .runtime import GeneratedParser, GeneratedLexer
    if len({escaped(rule) for rule in rules}) != len(rules):
        raise GrammarError('Parser rule names collide after Python escaping')
    for rule in rules:
        if hasattr(GeneratedParser, escaped(rule)) or rule in {'atn', 'ruleNames', 'symbolicNames', 'literalNames', 'grammarFileName'}:
            raise GrammarError(f'Parser rule conflicts with runtime attribute: {rule}')
    for value in [r.name for r in lexer] + declared + (list(vocabulary.names) if vocabulary else []) + modes[1:] + list(channels)[2:]:
        if (value.startswith('T__') and value in declared or
                hasattr(GeneratedParser, escaped(value)) or hasattr(GeneratedLexer, escaped(value))):
            raise GrammarError(f'Name conflicts with runtime attribute: {value}')
    literals = {}
    for node in rules.values():
        for tag, value in walk(node):
            if tag not in ('lit', 'ref', 'call', 'seq', 'alt', '?', '*', '+', '??', '*?', '+?', 'not', 'wildcard', 'assoc', 'altlabel', 'label', 'invoke', 'action', 'predicate', 'fail'):
                raise GrammarError(f'Unsupported parser construct: {tag}')
            if tag == 'lit':
                literals.setdefault(value, None)
    tokens = dict(vocabulary.names) if vocabulary else {}
    imported_literals = dict(vocabulary.literals) if vocabulary else {}
    def next_type():
        return max([0, *tokens.values(), *imported_literals.values()])+1
    for token in declared:
        tokens.setdefault(token, next_type())
    implicit = []
    for text in literals:
        if text in imported_literals:
            literals[text] = imported_literals[text]
            continue
        if kind == 'parser':
            raise GrammarError(f'Parser literal {text!r} is missing from tokenVocab')
        explicit = next((r for r in lexer if not r.fragment and lexer_literal(r.node) == text), None)
        if explicit is None:
            token = next_type()
            index = len(implicit)
            while f'T__{index}' in tokens:
                index += 1
            implicit.append(LexerRule(f'T__{index}', ('lit', text), token_type=token))
            tokens[implicit[-1].name] = token
            literals[text] = token
    for rule in lexer:
        if not rule.fragment:
            # Rules retyped with -> type(...) do not receive their own token type.
            commands = [v[1] for k, v in walk(rule.node) if k == 'commands']
            retyped = bool(commands) and any(c in ('type', 'more') for c, _ in commands[0])
            if not retyped:
                tokens.setdefault(rule.name, next_type())
            rule.token_type = tokens.get(rule.name, 0)
    for text in literals:
        if literals[text] is None:
            rule = next(r for r in lexer if not r.fragment and lexer_literal(r.node) == text)
            literals[text] = tokens[rule.name]
    for node in rules.values():
        for tag, value in walk(node):
            if tag == 'ref' and value != 'EOF' and value[0].isupper():
                tokens.setdefault(value, next_type())
    if len({escaped(token) for token in tokens}) != len(tokens):
        raise GrammarError('Token names collide after Python escaping')
    for node in rules.values():
        for tag, value in walk(node):
            reference = value[0] if tag in ('invoke', 'call') else value
            if tag in ('ref', 'invoke', 'call') and reference not in rules and reference not in tokens and reference != 'EOF':
                raise GrammarError(f'Undefined reference: {value}')
    grammar = Grammar(name, rules, implicit+lexer, tokens, literals, kind=kind, modes=modes, channels=channels)
    grammar.attributes = source.attributes
    grammar.named_actions = source.named_actions
    grammar.rule_actions = source.rule_actions
    grammar.rule_catches = source.rule_catches
    grammar.options = source.options
    prepare(grammar)
    from .actions import prepare_actions
    prepare_actions(grammar)
    # Preserve the entire external vocabulary, including unused literal aliases.
    grammar.literals = {**imported_literals, **grammar.literals}
    grammar.context_rules = deepcopy(grammar.rules)
    if grammar.kind != 'parser':
        validate_lexer(grammar)
    rewrite_left_recursion(grammar)
    validate_grammar(grammar)
    return grammar


def validate_lexer(grammar):
    by_name = {rule.name: rule for rule in grammar.lexer}
    nullable = {name: False for name in by_name}
    def check(node):
        kind, value = node
        if kind in ('label', 'altlabel'):
            check(value[2] if kind == 'label' else value[1])
        if kind in ('action', 'predicate'):
            return True
        if kind in ('lit', 'range', 'wildcard'):
            return False
        if kind == 'set':
            character_set(value)
            return False
        if kind == 'not':
            from .characters import negated_set
            negated_set(value)
            return False
        if kind == 'ref':
            if value == 'EOF':
                return False
            if value not in by_name:
                raise GrammarError(f'Undefined lexer reference: {value}')
            return nullable[value]
        if kind in ('seq', 'alt'):
            values = [check(child) for child in value]
            return all(values) if kind == 'seq' else any(values)
        if kind in ('?', '*', '+', '??', '*?', '+?'):
            empty = check(value)
            if kind[0] in ('*', '+') and empty:
                raise GrammarError('Nullable lexer repetition')
            return empty or kind[0] != '+'
        if kind == 'commands':
            return check(value[0])
        raise GrammarError(f'Unsupported lexer construct: {kind}')
    while True:
        updated = {name: check(rule.node) for name, rule in by_name.items()}
        if updated == nullable:
            break
        nullable.update(updated)

    def leading(node):
        kind, value = node
        if kind == 'ref':
            return {value} if value in by_name else set()
        if kind == 'commands':
            return leading(value[0])
        if kind in ('?', '*', '+', '??', '*?', '+?'):
            return leading(value)
        result = set()
        if kind in ('seq', 'alt'):
            for child in value:
                result |= leading(child)
                if kind == 'seq' and not check(child):
                    break
        return result

    edges, visited = {name: leading(rule.node) for name, rule in by_name.items()}, set()
    def visit(name, path):
        if name in path:
            raise GrammarError('Left-recursive lexer rules: '+' -> '.join(path+[name]))
        if name not in visited:
            for target in edges[name]:
                visit(target, path+[name])
            visited.add(name)
    for name in by_name:
        visit(name, [])
    for rule in grammar.lexer:
        if rule.node[0] == 'alt' and any(k == 'commands' for k, _ in walk(rule.node)):
            raise GrammarError('Group lexer alternatives before applying commands')
        if nullable[rule.name] and not rule.fragment:
            raise GrammarError(f'Lexer rule {rule.name} can match empty input')
        outer = rule.node[1] if rule.node[0] == 'alt' else [rule.node]
        for alternative in outer:
            body = alternative[1][0] if alternative[0] == 'commands' else alternative
            if any(k == 'commands' for k, _ in walk(body)):
                raise GrammarError('Lexer commands must be on outermost alternatives')
        for tag, value in walk(rule.node):
            if tag != 'commands':
                continue
            if rule.fragment:
                raise GrammarError('Fragments cannot have lexer commands')
            seen = set()
            for command, argument in value[1]:
                if command in seen:
                    raise GrammarError(f'Duplicate lexer command: {command}')
                seen.add(command)
                if command in ('skip', 'more', 'popMode'):
                    if argument is not None:
                        raise GrammarError(f'{command} takes no argument')
                elif command in ('mode', 'pushMode', 'type', 'channel'):
                    table = grammar.modes if command in ('mode', 'pushMode') else grammar.tokens if command == 'type' else grammar.channels
                    if argument not in table and not (argument and argument.isdigit()):
                        raise GrammarError(f'Unknown {command} target: {argument}')
                else:
                    raise GrammarError(f'Unsupported lexer command: {command}')
            if len(seen & {'skip', 'more', 'type'}) > 1:
                raise GrammarError('skip, more, and type cannot be combined')
            if 'channel' in seen and seen & {'skip', 'more'}:
                raise GrammarError('channel cannot be combined with skip or more')
    for mode in grammar.modes:
        if not any(r.mode == mode and not r.fragment for r in grammar.lexer):
            raise GrammarError(f'Lexer mode {mode} has no token rules')
    constants = list(grammar.tokens) + grammar.modes[1:] + list(grammar.channels)[2:]
    if len(constants) != len(set(constants)):
        raise GrammarError('Token, mode, and channel names must be distinct')


def rewrite_left_recursion(grammar):
    """Rewrite immediate recursion to ANTLR's primary + precedence-loop form.

    Alternative positions determine precedence, including intervening primary
    alternatives. Only the rightmost operand of binary/prefix alternatives gets
    a precedence argument; parenthesized/internal references retain precedence 0.
    """
    for name, node in list(grammar.rules.items()):
        alternatives = node[1] if node[0] == 'alt' else [node]
        unpacked = [alt_parts(alt) for alt in alternatives]
        recursive = any(alt[0] == 'seq' and alt[1] and element(alt[1][0]) == ('ref', name)
                        for _, _, alt in unpacked)
        if not recursive:
            if any(kind == 'assoc' for kind, _ in walk(node)):
                raise GrammarError('assoc is supported only on direct-left-recursive binary alternatives')
            continue
        if grammar.attributes[name]['args']:
            raise GrammarError('Arguments on left-recursive rules are not supported')
        if grammar.rule_catches.get(name) or 'finally' in grammar.rule_actions.get(name, {}):
            raise GrammarError('Custom catch/finally clauses on left-recursive rules require a nonrecursive wrapper rule')
        primary, binary_operators, suffix_operators = [], [], []
        for index, (alt_label, assoc, alt) in enumerate(unpacked):
            if alt[0] != 'seq' or any(kind == 'assoc' for kind, _ in walk(alt)):
                raise GrammarError(f'Unsupported nested associativity option in {name}')
            elements = list(alt[1])
            operand_index = len(elements)-1
            while operand_index >= 0 and elements[operand_index][0] in ('action', 'predicate'):
                operand_index -= 1
            precedence = len(alternatives) - index
            left = bool(elements and element(elements[0]) == ('ref', name))
            if left:
                first = elements.pop(0)
                operand_index -= 1
                left_binding = [('leftbind', first[1][:2])] if first[0] == 'label' else []
                if not elements:
                    raise GrammarError(f'Left-recursive alternative in {name} has no suffix')
                binary = operand_index >= 0 and element(elements[operand_index]) == ('ref', name)
                if assoc is not None and not binary:
                    raise GrammarError('assoc is supported only on direct-left-recursive binary alternatives')
                if binary:
                    operand = ('call', (name, precedence if assoc == 'right' else precedence + 1))
                    original = elements[operand_index]
                    elements[operand_index] = ('label', (*original[1][:2], operand)) if original[0] == 'label' else operand
                target = binary_operators if binary else suffix_operators
                body = ('seq', left_binding + [('enter', None), ('prec', precedence)] + elements)
                target.append(('altlabel', (alt_label, body)) if alt_label else body)
            else:
                if assoc is not None:
                    raise GrammarError('assoc is supported only on direct-left-recursive binary alternatives')
                # Prefix operators ending in an operand bind at this
                # alternative's precedence; parentheses do not end in a ref.
                if operand_index > 0 and element(elements[operand_index]) == ('ref', name):
                    operand = ('call', (name, precedence))
                    original = elements[operand_index]
                    elements[operand_index] = ('label', (*original[1][:2], operand)) if original[0] == 'label' else operand
                body = ('seq', elements)
                primary.append(('altlabel', (alt_label, body)) if alt_label else body)
        if not primary:
            raise GrammarError(f'Left-recursive rule {name} needs a primary alternative')
        base = primary[0] if len(primary) == 1 else ('alt', primary)
        # ANTLR emits binary alternatives before suffix alternatives, retaining
        # the original alternative numbers for their precedence predicates.
        operators = binary_operators + suffix_operators
        loop = operators[0] if len(operators) == 1 else ('alt', operators)
        grammar.rules[name] = ('seq', [base, ('*', loop)])
        grammar.left_recursive.add(name)


def validate_grammar(grammar):
    """Reject remaining recursion cycles and nullable closures after rewriting."""
    rules = grammar.rules
    nullable = {name: False for name in rules}
    first = {name: set() for name in rules}

    def info(node):
        kind, value = node
        if kind == 'wildcard':
            return set(grammar.tokens.values()) | set(grammar.literals.values()), False
        if kind == 'not':
            from .annotations import token_block
            if not token_block(value, grammar):
                raise GrammarError('Parser negation requires token/literal alternatives')
            excluded, _ = info(value)
            return (set(grammar.tokens.values()) | set(grammar.literals.values())) - excluded, False
        if kind == 'lit':
            return {grammar.literals[value]}, False
        if kind in ('label', 'altlabel'):
            return info(value[2] if kind == 'label' else value[1])
        if kind == 'invoke':
            return info(('ref', value[0]))
        if kind in ('leftbind', 'enter', 'action', 'predicate'):
            return set(), True
        if kind == 'prec':
            return set(), True
        if kind in ('ref', 'call'):
            if kind == 'call':
                value = value[0]
            if value in rules:
                return first[value], nullable[value]
            return {-1 if value == 'EOF' else grammar.tokens[value]}, False
        if kind in ('?', '*', '+', '??', '*?', '+?'):
            f, n = info(value)
            return f, n or kind[0] != '+'
        result, empty = set(), kind == 'seq'
        for child in value:
            f, n = info(child)
            result |= f
            if kind == 'seq' and not n:
                return result, False
            if kind == 'alt':
                empty |= n
        return result, empty

    while True:
        updated = {name: info(node) for name, node in rules.items()}
        if all(first[n] == f and nullable[n] == e for n, (f, e) in updated.items()):
            break
        for name, (f, e) in updated.items():
            first[name], nullable[name] = f, e

    for name in grammar.left_recursive:
        if nullable[name]:
            raise GrammarError(f'Left-recursive rule {name} needs a non-nullable primary')

    def leading(node):
        kind, value = node
        if kind in ('label', 'altlabel'):
            return leading(value[2] if kind == 'label' else value[1])
        if kind == 'invoke':
            return leading(('ref', value[0]))
        if kind in ('ref', 'call'):
            if kind == 'call':
                value = value[0]
            return {value} if value in rules else set()
        if kind in ('?', '*', '+', '??', '*?', '+?'):
            return leading(value)
        result = set()
        if kind in ('seq', 'alt'):
            for child in value:
                result |= leading(child)
                if kind == 'seq' and not info(child)[1]:
                    break
        return result

    edges = {name: leading(node) for name, node in rules.items()}
    visited = set()
    def visit(name, path):
        if name in path:
            raise GrammarError('Indirect or unsupported left recursion: ' + ' -> '.join(path + [name]))
        if name in visited:
            return
        for child in edges[name]:
            visit(child, path + [name])
        visited.add(name)
    for name in rules:
        visit(name, [])

    def check(node):
        kind, value = node
        if kind in ('label', 'altlabel'):
            check(value[2] if kind == 'label' else value[1])
        if kind in ('alt', 'seq'):
            for child in value:
                check(child)
        elif kind in ('?', '*', '+', '??', '*?', '+?'):
            f, n = info(value)
            if -1 in f and kind[0] != '?':
                raise GrammarError('EOF inside repetition/optional expressions is unsupported')
            if kind[0] in ('*', '+') and n:
                raise GrammarError('Nullable repetition is unsupported')
            check(value)
    for node in rules.values():
        check(node)
    return {name: sorted(values) for name, values in first.items()}, nullable
