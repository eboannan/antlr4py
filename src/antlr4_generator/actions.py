"""Compile trusted grammar Python into ordinary generated methods.

Grammar actions are executable source code, just as with ANTLR's Python target.
They are validated while generating and executed only by generated recognizers.
"""
import ast
import io
import re
import symtable
import textwrap
import tokenize

from .errors import GrammarError
from .naming import escaped


def normalize(code):
    return textwrap.dedent(code).strip()


def references(code):
    """Locate $ references outside Python strings and comments."""
    lines = code.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, IndentationError) as exc:
        raise GrammarError('Malformed Python in grammar action') from exc
    for token in tokens:
        if token.string != '$' or token.type in (tokenize.STRING, tokenize.COMMENT):
            continue
        start = offsets[token.start[0]-1] + token.start[1]
        match = re.match(r'\$([A-Za-z_][A-Za-z_0-9]*)(?:::([A-Za-z_][A-Za-z_0-9]*)|(?:\.([A-Za-z_][A-Za-z_0-9]*))?)', code[start:])
        if not match or code[start+len(match[0]):].startswith('::'):
            raise GrammarError('Malformed action attribute reference')
        name = match[1]+('::'+match[2] if match[2] else '')
        yield start, start+len(match[0]), name, match[3]


def translate(code, rule, attributes, labels, implicit, lexer=False, nonlocals=None):
    code = normalize(code)
    replacements = []
    for start, end, name, prop in references(code):
        if lexer:
            raise GrammarError('Lexer actions use self.text/self.type/etc., not $ attributes')
        elif '::' in name:
            owner, attribute = name.split('::')
            if owner not in (nonlocals or {}) or attribute not in nonlocals[owner][1]:
                raise GrammarError(f'Unknown nonlocal rule attribute: ${name}')
            replacement = f'self.getInvokingContext({nonlocals[owner][0]}).{escaped(attribute)}'
        elif name in attributes:
            replacement = 'localctx.'+escaped(name)+('.'+prop if prop else '')
        elif name in {'ctx', 'text', 'start', 'stop', 'parser'} or name == rule:
            builtins = {'ctx': 'localctx', 'parser': 'self', 'start': 'localctx.start',
                        'stop': 'localctx.stop',
                        'text': 'self._input.getText(localctx.start, self._input.LT(-1))'}
            if name == rule:
                if prop in attributes:
                    replacement = 'localctx.'+escaped(prop)
                elif prop in builtins:
                    replacement = builtins[prop]
                else:
                    raise GrammarError(f'Unknown current-rule attribute: ${rule}.{prop}')
            else:
                replacement = builtins[name]+('.'+prop if prop else '')
        elif name in labels or name in implicit:
            field, target, many = labels[name] if name in labels else implicit[name]
            base = 'localctx.'+escaped(field)
            if not prop:
                replacement = base
            elif many:
                raise GrammarError('List labels cannot have grammar attribute properties')
            elif target == 'token':
                properties = {'text': ('text', 'None'), 'type': ('type', '0'),
                              'line': ('line', '0'), 'pos': ('column', '0'),
                              'channel': ('channel', '0'), 'index': ('tokenIndex', '0')}
                if prop == 'int':
                    replacement = f'(0 if {base} is None else int({base}.text))'
                elif prop in properties:
                    attr, default = properties[prop]
                    replacement = f'({default} if {base} is None else {base}.{attr})'
                else:
                    raise GrammarError(f'Unknown token attribute: {prop}')
            elif prop == 'text':
                replacement = f'(None if {base} is None else self._input.getText({base}.start, {base}.stop))'
            elif prop == 'ctx':
                replacement = base
            elif prop == 'parser':
                replacement = 'self'
            else:
                replacement = f'(None if {base} is None else {base}.{escaped(prop)})'
        else:
            raise GrammarError(f'Unknown action attribute: ${name}')
        replacements.append((start, end, replacement))
    for start, end, replacement in reversed(replacements):
        code = code[:start]+replacement+code[end:]
    return code


def checked(code, predicate=False):
    class ControlFlow(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            pass
        visit_AsyncFunctionDef = visit_FunctionDef
        visit_Lambda = visit_FunctionDef

        def visit_Yield(self, node):
            raise GrammarError('Yielding from recognizer actions is unsupported; use a visitor generator')
        visit_YieldFrom = visit_Yield

    try:
        if predicate:
            parsed = ast.parse(code, mode='eval')
            ControlFlow().visit(parsed)
            compile('def _predicate(self, localctx):\n'+textwrap.indent('return ('+code+'\n)', '    '),
                    '<grammar predicate>', 'exec')
        else:
            parsed = ast.parse(code or 'pass')
            ControlFlow().visit(parsed)
            if not parsed.body:
                code += '\npass'
            compile('def _action(self, localctx):\n'+textwrap.indent(code or 'pass', '    '),
                    '<grammar action>', 'exec')
    except SyntaxError as exc:
        raise GrammarError(f'Invalid Python {"predicate" if predicate else "action"}: {exc.msg}') from exc
    return code


def prepare_actions(grammar):
    from .grammar import walk
    from .annotations import element
    grammar.code = {target: {'actions': [], 'arguments': [], 'predicates': [], 'predicateTexts': {}, 'predicateFailures': {}, 'hooks': {}, 'catches': {}, 'locals': {}, 'globals': {}}
                    for target in ('parser', 'lexer')}
    nonlocals = {rule: (index, {name for group in grammar.attributes[rule].values() for name, _ in group})
                for index, rule in enumerate(grammar.rules)}
    for key, code in grammar.named_actions.items():
        normalized = normalize(code)
        if list(references(normalized)):
            raise GrammarError('Grammar header/members actions cannot use rule attributes')
        if key[1] == 'header':
            try:
                compile(normalized, '<grammar header>', 'exec')
            except SyntaxError as exc:
                raise GrammarError(f'Invalid Python header: {exc.msg}') from exc
        else:
            try:
                compile('class _Members:\n'+textwrap.indent(normalized+'\npass', '    '),
                        '<grammar members>', 'exec')
            except SyntaxError as exc:
                raise GrammarError(f'Invalid Python members: {exc.msg}') from exc
        grammar.named_actions[key] = normalized

    def prepare_rule(rule, node, index, lexer=False):
        target = 'lexer' if lexer else 'parser'
        table = grammar.code[target]
        attributes = {n for group in grammar.attributes.get(rule, {}).values() for n, _ in group}
        labels, implicit = {}, {}
        for kind, value in walk(node):
            if kind == 'label':
                name, many, child = value
                child = element(child)
                reference = child[1][0] if child[0] == 'invoke' else child[1]
                is_rule = child[0] in ('invoke', 'ref') and isinstance(reference, str) and reference in grammar.rules
                labels[name] = (name, 'rule' if is_rule else 'token', many)
        codes = [value for kind, value in walk(node) if kind in ('action', 'predicate')]
        codes += list(grammar.rule_actions.get(rule, {}).values())
        codes += [body for _, body in grammar.rule_catches.get(rule, [])]
        codes += [argument for kind, value in walk(node) if kind == 'invoke' for argument in value[1]]
        codes += [value[1][1:-1] for kind, value in walk(node)
                  if kind == 'fail' and value[1].startswith('{')]
        requested = {name for code in codes for _, _, name, _ in references(normalize(code))}
        for kind, value in walk(node):
            if kind not in ('ref', 'invoke'):
                continue
            name = value[0] if kind == 'invoke' else value
            if name in requested and name != rule and name not in labels and name not in attributes:
                implicit[name] = ('_implicit_'+name, 'rule' if name in grammar.rules else 'token', False)

        def code_for(code, predicate=False):
            return checked(translate(code, rule, attributes, labels, implicit, lexer, nonlocals), predicate)

        hooks = {hook: code_for(code) for hook, code in grammar.rule_actions.get(rule, {}).items()}
        if hooks:
            table['hooks'][index] = hooks
        catches, bindings = [], []
        for header, body in grammar.rule_catches.get(rule, []):
            header = header.strip()
            try:
                parsed = ast.parse('try:\n pass\nexcept '+header+':\n pass')
                handler = parsed.body[0].handlers[0]
            except SyntaxError as exc:
                raise GrammarError(f'Invalid Python catch declaration: {header}') from exc
            if handler.name in ('self', 'localctx', '_error'):
                raise GrammarError(f'Reserved catch binding: {handler.name}')
            if catches and not catches[-1][0]:
                raise GrammarError('A catch-all clause must be last')
            if handler.name:
                bindings.append(handler.name)
            catches.append((header, code_for(body), handler.name))
        if catches:
            table['catches'][index] = catches

        def rewrite(node):
            kind, value = node
            if kind == 'fail':
                predicate = rewrite(value[0])
                failure = value[1]
                if failure.startswith("'"):
                    from .characters import literal
                    code = repr(literal(failure))
                elif failure.startswith('{'):
                    code = code_for(failure[1:-1], True)
                else:
                    raise GrammarError('Predicate fail requires a string or Python expression block')
                table['predicateFailures'][predicate[1]['index']] = code
                return predicate
            if kind == 'invoke':
                arguments = [code_for(text, True) for text in value[1]]
                number = len(table['arguments'])
                table['arguments'].append((index, '['+', '.join(arguments)+']'))
                invocation = ('invoke', (value[0], number))
                if value[0] in implicit:
                    return 'label', (implicit[value[0]][0], False, invocation)
                return invocation
            if kind in ('action', 'predicate'):
                code = code_for(value, kind == 'predicate')
                collection = table['predicates' if kind == 'predicate' else 'actions']
                number = len(collection)
                collection.append((index, code))
                if kind == 'predicate':
                    table['predicateTexts'][number] = normalize(value)
                # Only local-context predicates can depend on rule attributes.
                dependent = bool(list(references(normalize(value)))) or any(
                    isinstance(n, ast.Name) and n.id == 'localctx'
                    for n in ast.walk(ast.parse(code or 'pass')))
                return kind, {'index': number, 'dependent': dependent}
            if kind in ('seq', 'alt'):
                return kind, [rewrite(child) for child in value]
            if kind in ('?', '*', '+', '??', '*?', '+?', 'not'):
                return kind, rewrite(value)
            if kind in ('assoc', 'altlabel'):
                return kind, (value[0], rewrite(value[1]))
            if kind == 'label':
                return kind, (*value[:2], rewrite(value[2]))
            if kind == 'commands':
                return kind, (rewrite(value[0]), value[1])
            name = value[0] if kind == 'invoke' else value
            if kind in ('ref', 'invoke') and name in implicit:
                return 'label', (implicit[name][0], False, node)
            return node
        rewritten = rewrite(node)
        if not lexer:
            bodies = ([name+' = None' for name in bindings] + list(hooks.values()) +
                      [code for owner, code in table['actions'] if owner == index] +
                      [code for owner, code in table['arguments'] if owner == index] +
                      [code for _, code, _ in catches])
            combined = '\n'.join(bodies) or 'pass'
            try:
                symbols = symtable.symtable('def _rule(self, localctx):\n'+textwrap.indent(combined, '    '),
                                           '<grammar actions>', 'exec').get_children()[0]
                table['locals'][index] = sorted({escaped(name) for name, _ in grammar.attributes[rule]['args']} |
                                               {symbol.get_name() for symbol in symbols.get_symbols()
                                                if symbol.is_local() and not symbol.is_parameter()})
                table['globals'][index] = sorted(symbol.get_name() for symbol in symbols.get_symbols()
                                                if symbol.is_declared_global())
            except SyntaxError as exc:
                raise GrammarError(f'Invalid Python action scope: {exc.msg}') from exc
        return rewritten

    for index, (rule, node) in enumerate(grammar.rules.items()):
        grammar.rules[rule] = prepare_rule(rule, node, index)
    for index, rule in enumerate(grammar.lexer):
        rule.node = prepare_rule(rule.name, rule.node, index, lexer=True)


def methods(grammar, target):
    """Emit code without eval/exec in installed recognizers."""
    table = grammar.code[target]
    source = ''

    def action_body(rule, code, bound=()):
        names = table['locals'].get(rule, [])
        globals_ = table['globals'].get(rule, [])
        declarations = ('global '+', '.join(globals_)+'\n') if globals_ else ''
        if not names:
            return declarations+(code or 'pass')
        body = declarations+''.join(f'if {name!r} in localctx._actionLocals:\n'
                       f'    {name} = localctx._actionLocals[{name!r}]\n' for name in names if name not in bound)
        body += 'try:\n'+textwrap.indent(code or 'pass', '    ')+'\nfinally:\n'
        for name in names:
            body += (f'    try:\n        localctx._actionLocals[{name!r}] = {name}\n'
                     f'    except UnboundLocalError:\n        localctx._actionLocals.pop({name!r}, None)\n')
        return body

    for category, prefix in [('actions', '_action'), ('predicates', '_predicate')]:
        for index, (rule, code) in enumerate(table[category]):
            body = 'return ('+code+'\n)' if category == 'predicates' else action_body(rule, code)
            source += f'\n    def {prefix}_{index}(self, localctx):\n'+textwrap.indent(body, '        ')+'\n'
    if table['actions']:
        source += '\n    def action(self, localctx, ruleIndex, actionIndex):\n'
        if target == 'parser':
            source += "        if ruleIndex in self._scopeMethods:\n            return self._scope_execute(ruleIndex, 'action', actionIndex, localctx)\n"
        source += '        return ('+', '.join(f'self._action_{i}' for i in range(len(table['actions'])))+',)[actionIndex](localctx)\n'
    if table['predicates']:
        source += f'\n    _predicateTexts = {table["predicateTexts"]!r}\n'
        source += '\n    _predicateFailures = {'+', '.join(
            repr(i)+': (lambda self, localctx: '+code+')' for i, code in table['predicateFailures'].items())+'}\n'
        source += '\n    def sempred(self, localctx, ruleIndex, predIndex):\n'
        source += '        return ('+', '.join(f'self._predicate_{i}' for i in range(len(table['predicates'])))+',)[predIndex](localctx)\n'
    for index, hooks in table['hooks'].items():
        for hook, code in hooks.items():
            source += f'\n    def _{hook}_{index}(self, localctx):\n'+textwrap.indent(action_body(index, code), '        ')+'\n'
    if table['hooks']:
        source += '\n    _ruleHooks = {\n'
        for index, hooks in table['hooks'].items():
            source += f'        {index}: '+'{'+', '.join(repr(hook)+f': _{hook}_{index}' for hook in hooks)+'},\n'
        source += '    }\n'
    for index, catches in table['catches'].items():
        source += (f'\n    def _catch_{index}(self, localctx, _error):\n'
                   f"        if {index} in self._scopeMethods:\n            return self._scope_execute({index}, 'catch', 0, localctx, _error)\n"
                   '        try:\n            raise _error\n')
        for header, code, binding in catches:
            source += '        except '+header+':\n'
            body = action_body(index, code, (binding,))
            if binding:
                body = ('try:\n'+textwrap.indent(body, '    ')+'\nfinally:\n'
                        f'    localctx._actionLocals.pop({binding!r}, None)')
            source += textwrap.indent(body, '            ')+'\n            return True\n'
        if catches[-1][0]:
            source += '        except BaseException:\n            return False\n'
    if table['catches']:
        source += '\n    _ruleCatches = {'+', '.join(f'{i}: _catch_{i}' for i in table['catches'])+'}\n'
    for index, (rule, code) in enumerate(table['arguments']):
        source += (f'\n    def _arguments_{index}(self, localctx):\n'
                   f"        if {rule} in self._scopeMethods:\n            return self._scope_execute({rule}, 'arguments', {index}, localctx)\n")+textwrap.indent(
            action_body(rule, 'return '+code), '        ')+'\n'
    if table['arguments']:
        source += '\n    _argumentMethods = ('+', '.join(f'_arguments_{i}' for i in range(len(table['arguments'])))+',)\n'
    if target == 'parser':
        from .action_sessions import sessions
        source += sessions(grammar)
    members = grammar.named_actions.get((target, 'members'), '')
    if members:
        source += '\n'+textwrap.indent(members, '    ')+'\n'
    return source
