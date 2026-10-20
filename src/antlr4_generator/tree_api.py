"""Emit typed/labeled contexts and standard Python visitor/listener hooks."""
from collections import Counter
from antlr4 import ParserRuleContext
from .annotations import alt_parts
from .errors import GrammarError
from .grammar import walk
from .naming import escaped


def title(name):
    return name[0].upper() + name[1:]


def cardinalities(node):
    kind, value = node
    if kind == 'ref':
        return Counter({value: 1})
    if kind in ('invoke', 'call'):
        return Counter({value[0]: 1})
    if kind in ('assoc', 'altlabel'):
        return cardinalities(value[1])
    if kind == 'label':
        return cardinalities(value[2])
    if kind in ('?', '*', '+', '??', '*?', '+?'):
        counts = cardinalities(value)
        return Counter({key: 2 if kind[0] in ('*', '+') else count for key, count in counts.items()})
    result = Counter()
    if kind in ('alt', 'seq'):
        for child in value:
            for key, count in cardinalities(child).items():
                result[key] = min(2, result[key]+count) if kind == 'seq' else max(result[key], count)
    return result


def variants(node):
    alternatives = node[1] if node[0] == 'alt' else [node]
    groups = {}
    for alt in alternatives:
        label, _, body = alt_parts(alt)
        if label:
            groups.setdefault(label, []).append(body)
    return {label: ('alt', bodies) for label, bodies in groups.items()}


def label_fields(node):
    return {escaped(value[0]): value[1] for kind, value in walk(node) if kind == 'label'}


def dispatch(suffix):
    return (f'        def enterRule(self, listener):\n'
            f'            if hasattr(listener, "enter{suffix}"):\n'
            f'                listener.enter{suffix}(self)\n\n'
            f'        def exitRule(self, listener):\n'
            f'            if hasattr(listener, "exit{suffix}"):\n'
            f'                listener.exit{suffix}(self)\n\n'
            '        def accept(self, visitor):\n'
            f'            if hasattr(visitor, "visit{suffix}"):\n'
            f'                return visitor.visit{suffix}(self)\n'
            '            return visitor.visitChildren(self)\n\n')


def getters(grammar, node):
    source = ''
    for reference, count in cardinalities(node).items():
        if (hasattr(ParserRuleContext, escaped(reference)) or reference in
                {'parser', 'start', 'stop', 'children', 'exception', 'ruleIndex'}):
            raise GrammarError(f'Context accessor conflicts with a runtime attribute: {reference}')
        is_rule = reference in grammar.rules
        argument = f'self.parser.{title(reference)}Context' if is_rule else (
            '-1' if reference == 'EOF' else f'self.parser.{escaped(reference)}')
        single = 'getTypedRuleContext' if is_rule else 'getToken'
        plural = 'getTypedRuleContexts' if is_rule else 'getTokens'
        if count == 1:
            source += (f'        def {escaped(reference)}(self):\n'
                       f'            return self.{single}({argument}, 0)\n\n')
        else:
            source += (f'        def {escaped(reference)}(self, i=None):\n'
                       '            if i is None:\n'
                       f'                return self.{plural}({argument})\n'
                       f'            return self.{single}({argument}, i)\n\n')
    return source


def context_source(grammar):
    source, alt_classes = '', {}
    generated = [title(name)+'Context' for name in grammar.rules]
    for node in grammar.context_rules.values():
        generated += [title(label)+'Context' for label in variants(node)]
    if len(generated) != len(set(generated)) or set(generated) & (set(grammar.tokens) | set(grammar.rules)):
        raise GrammarError('Rule context names conflict with grammar symbols')
    if {'RULE_'+name for name in grammar.rules} & set(grammar.tokens):
        raise GrammarError('Rule-index constants conflict with tokens')
    for index, (name, node) in enumerate(grammar.context_rules.items()):
        context, suffix = title(name)+'Context', title(name)
        attrs, labeled = grammar.attributes[name], variants(node)
        args = attrs['args']
        all_attrs = [item for group in attrs.values() for item in group]
        ctor_args = ''.join(', '+escaped(field)+'=None' for field, _ in args)
        source += (f'    RULE_{name} = {index}\n\n'
                   f'    class {context}(_GeneratedRuleContext):\n'
                   f'        def __init__(self, parser, parent=None, invokingState=-1{ctor_args}):\n'
                   f'            super().__init__(parent, invokingState, {index})\n'
                   '            self.parser = parser\n')
        source += '            self._actionLocals = {'+', '.join(repr(escaped(n))+': '+escaped(n) for n, _ in args)+'}\n'
        for field, default in all_attrs:
            source += f'            self.{escaped(field)} = '+(escaped(field) if (field, default) in args else default or 'None')+'\n'
        if not labeled:
            for field, many in label_fields(node).items():
                source += f'            self.{field} = '+('[]' if many else 'None')+'\n'
        source += '\n'
        if labeled:
            source += ('        def copyFrom(self, ctx):\n            super().copyFrom(ctx)\n'
                       '            self._actionLocals = ctx._actionLocals\n' +
                       ''.join(f'            self.{escaped(field)} = ctx.{escaped(field)}\n' for field, _ in all_attrs)+'\n')
        else:
            source += getters(grammar, node)+dispatch(suffix)
        for label, body in labeled.items():
            cls = title(label)+'Context'
            alt_classes[label] = cls
            source += (f'    class {cls}({context}):\n'
                       '        def __init__(self, parser, ctx):\n'
                       '            super().__init__(parser)\n')
            for field, many in label_fields(body).items():
                source += f'            self.{field} = '+('[]' if many else 'None')+'\n'
            source += '            self.copyFrom(ctx)\n\n'+getters(grammar, body)+dispatch(title(label))
    source += '    _contextTypes = (' + ', '.join(title(n)+'Context' for n in grammar.rules) + ',)\n'
    source += '    _altContextTypes = {' + ', '.join(repr(k)+': '+v for k, v in alt_classes.items())+'}\n'
    source += f'    _ruleArgumentNames = {[[escaped(n) for n, _ in grammar.attributes[r]["args"]] for r in grammar.rules]!r}\n'
    source += '    _ruleArgumentDefaults = {' + ', '.join(
        f'{i}: '+'{'+', '.join(repr(escaped(n))+': '+v for n, v in grammar.attributes[r]['args'] if v is not None)+'}'
        for i, r in enumerate(grammar.rules))+'}\n'
    source += '    _deferRecursionEnter = True\n'
    return source


def hooks(grammar):
    for name, node in grammar.context_rules.items():
        labeled = variants(node)
        yield from (list(labeled) if labeled else [name])


def visitor_source(grammar):
    source = ('# Generated Python visitor.\nfrom antlr4 import ParseTreeVisitor\n\n'
              f'class {grammar.name}Visitor(ParseTreeVisitor):\n')
    for name in hooks(grammar):
        source += f'    def visit{title(name)}(self, ctx):\n        return self.visitChildren(ctx)\n\n'
    return source


def listener_source(grammar):
    source = ('# Generated Python listener.\nfrom antlr4 import ParseTreeListener\n\n'
              f'class {grammar.name}Listener(ParseTreeListener):\n')
    for name in hooks(grammar):
        for event in ('enter', 'exit'):
            source += f'    def {event}{title(name)}(self, ctx):\n        pass\n\n'
    return source
