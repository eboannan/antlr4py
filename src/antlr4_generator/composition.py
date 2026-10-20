"""File resolution, delegate composition, and ANTLR token vocabularies."""
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import re

from .characters import literal
from .errors import GrammarError
from .grammar import parse_grammar, compile_grammar, lexer_literal


@dataclass
class Vocabulary:
    names: dict = field(default_factory=dict)
    literals: dict = field(default_factory=dict)


def read_vocabulary(path):
    """Read .tokens files from this generator or the original ANTLR tool."""
    result = Vocabulary()
    for number, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"(.+)=([0-9]+)", line.strip())
        if not match or int(match[2]) < 1:
            raise GrammarError(f'{path}:{number}: invalid token vocabulary entry')
        key, value = match[1], int(match[2])
        if re.fullmatch(r"'(?:\\.|[^'\\])*'", key):
            key, table = literal(key), result.literals
        elif re.fullmatch(r'[A-Z][A-Za-z_0-9]*', key) and key != 'EOF':
            table = result.names
        else:
            raise GrammarError(f'{path}:{number}: invalid token name {key!r}')
        if key in table and table[key] != value:
            raise GrammarError(f'{path}:{number}: conflicting token definition for {key!r}')
        table[key] = value
    return result


def quote_literal(text):
    escapes = {'\\': '\\\\', "'": "\\'", '\n': '\\n', '\r': '\\r', '\t': '\\t',
               '\b': '\\b', '\f': '\\f'}
    return "'" + ''.join(escapes.get(c, c if c.isprintable() else f'\\u{{{ord(c):X}}}')
                          for c in text) + "'"


def vocabulary_text(grammar):
    lines = [f'{name}={value}' for name, value in grammar.tokens.items()]
    # Single-literal lexer rules provide aliases even without parser references.
    aliases = dict(grammar.literals)
    candidates, conflicts = {}, set()
    for rule in grammar.lexer:
        text = lexer_literal(rule.node)
        if rule.token_type and text is not None:
            if text in candidates and candidates[text] != rule.token_type:
                conflicts.add(text)
            candidates[text] = rule.token_type
    aliases.update({text: value for text, value in candidates.items() if text not in conflicts})
    lines += [f'{quote_literal(text)}={value}' for text, value in aliases.items()]
    return '\n'.join(lines) + ('\n' if lines else '')


def resolve(filename, directories, description):
    for directory in dict.fromkeys(Path(d).resolve() for d in directories):
        path = directory / filename
        if path.is_file():
            return path
    searched = ', '.join(str(Path(d)) for d in directories)
    raise GrammarError(f'Missing {description} {filename}; searched: {searched}')


def load_grammar(path, output_dir, library_dirs=(), *, encoding='utf-8', options=None):
    path = Path(path).resolve()
    libraries = [Path(d).resolve() for d in library_dirs]
    sources, active, seen = [], [], set()

    def visit(current, expected=None, parent_kind=None):
        current = current.resolve()
        if current in active:
            raise GrammarError('Grammar import cycle: ' + ' -> '.join(p.name for p in active+[current]))
        if current in seen:
            return
        source = parse_grammar(current.read_text(encoding=encoding))
        if expected and source.name != expected:
            raise GrammarError(f'Imported file {current} declares {source.name}, expected {expected}')
        if parent_kind and parent_kind != 'combined' and source.kind != parent_kind:
            raise GrammarError(f'{parent_kind} grammar cannot import {source.kind} grammar {source.name}')
        active.append(current)
        seen.add(current)
        sources.append(source)
        for name in source.imports:
            delegate = resolve(name+'.g4', [current.parent, *libraries, path.parent], 'grammar import')
            visit(delegate, name, source.kind)
        active.pop()

    visit(path)
    root = deepcopy(sources[0])
    if options:
        text = 'lexer grammar Overrides; options {' + ''.join(
            str(name)+'='+str(value).lower()+';' if isinstance(value, bool) else str(name)+'='+str(value)+';'
            for name, value in options.items()) + "} PLACEHOLDER:'a';"
        validated = parse_grammar(text)
        root.options.update(validated.options)
        root.token_vocab = root.options.get('tokenVocab')
    # Root overrides delegates. Among delegates, the first occurrence in import
    # preorder wins, matching ANTLR's integration order.
    lexer_names = {r.name for r in root.lexer}
    for delegate in sources[1:]:
        for name, node in delegate.rules.items():
            if name not in root.rules:
                root.rules[name] = deepcopy(node)
                root.attributes[name] = deepcopy(delegate.attributes.get(name, {}))
                root.rule_actions[name] = deepcopy(delegate.rule_actions.get(name, {}))
                if name in delegate.rule_catches:
                    root.rule_catches[name] = deepcopy(delegate.rule_catches[name])
        for rule in delegate.lexer:
            if rule.name not in lexer_names:
                root.lexer.append(deepcopy(rule))
                lexer_names.add(rule.name)
        from .actions import normalize
        for key, code in delegate.named_actions.items():
            root.named_actions[key] = '\n'.join(filter(None, [
                normalize(root.named_actions.get(key, '')), normalize(code)]))
        for name in delegate.declared:
            if name not in root.declared:
                root.declared.append(name)
        for name in delegate.modes[1:]:
            if root.kind != 'lexer':
                raise GrammarError('Imported lexer modes require a standalone lexer root')
            if name not in root.modes:
                root.modes.append(name)
        for name in list(delegate.channels)[2:]:
            root.channels.setdefault(name, len(root.channels))
    vocabulary = None
    if root.token_vocab:
        vocab_path = resolve(root.token_vocab+'.tokens',
                             [*libraries, output_dir, path.parent], 'token vocabulary')
        vocabulary = read_vocabulary(vocab_path)
    return compile_grammar(root, vocabulary)
