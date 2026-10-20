"""Emit persistent Python rule scopes without runtime eval/exec.

A suspended dispatcher keeps real Python closure cells alive between ATN action
positions. Exceptions are yielded to the ATN walker so the same scope remains
available to catch/finally clauses after an action fails.
"""
import ast
import textwrap
from .naming import escaped


def body(code):
    class Returns(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            return node
        visit_AsyncFunctionDef = visit_FunctionDef
        visit_Lambda = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Return(self, node):
            return ast.copy_location(ast.Raise(
                ast.Call(ast.Name('_ActionReturn', ast.Load()),
                         [node.value or ast.Constant(None)], []), None), node)
    tree = Returns().visit(ast.parse(code or 'pass'))
    # Globals apply to the whole native rule function, not one dispatch branch.
    class Globals(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            return node
        visit_AsyncFunctionDef = visit_FunctionDef
        visit_Lambda = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Global(self, node):
            return ast.copy_location(ast.Pass(), node)
    return ast.unparse(ast.fix_missing_locations(Globals().visit(tree)))


def sessions(grammar):
    table = grammar.code['parser']
    source, indices = '', []
    for rule, name in enumerate(grammar.rules):
        actions = [(i, code) for i, (owner, code) in enumerate(table['actions']) if owner == rule]
        arguments = [(i, code) for i, (owner, code) in enumerate(table['arguments']) if owner == rule]
        hooks = table['hooks'].get(rule, {})
        catches = table['catches'].get(rule, [])
        if not (actions or arguments or hooks or catches):
            continue
        indices.append(rule)
        source += f'\n    def _scope_{rule}(self, localctx):\n'
        scope = ''
        globals_ = table['globals'].get(rule, [])
        if globals_:
            scope += 'global '+', '.join(globals_)+'\n'
        for field, _ in grammar.attributes[name]['args']:
            field = escaped(field)
            scope += f'{field} = localctx.{field}\n'
        scope += ('_antlr_command = yield\nwhile True:\n'
                  '    _antlr_kind, _antlr_index, localctx, _antlr_error = _antlr_command\n'
                  '    _antlr_result = None\n    try:\n')
        branches = []
        for index, code in actions:
            branches.append((f"_antlr_kind == 'action' and _antlr_index == {index}", body(code)))
        for index, code in arguments:
            branches.append((f"_antlr_kind == 'arguments' and _antlr_index == {index}", '_antlr_result = '+code))
        for hook, code in hooks.items():
            if hook == 'finally':
                code = ('if _antlr_error is not None:\n'
                        '    try:\n        raise _antlr_error\n'
                        '    except BaseException:\n'+textwrap.indent(body(code), '        ')+'\n'
                        'else:\n'+textwrap.indent(body(code), '    '))
            else:
                code = body(code)
            branches.append((f'_antlr_kind == {hook!r}', code))
        if catches:
            code = 'try:\n    raise _antlr_error\n'
            for header, action, _ in catches:
                code += 'except '+header+':\n'+textwrap.indent(body(action), '    ')+'\n    _antlr_result = True\n'
            if catches[-1][0]:
                code += 'except BaseException:\n    _antlr_result = False\n'
            branches.append(("_antlr_kind == 'catch'", code))
        for i, (condition, code) in enumerate(branches):
            scope += '        '+('if ' if i == 0 else 'elif ')+condition+':\n'
            scope += textwrap.indent(code, '            ')+'\n'
        scope += ('    except BaseException as _antlr_failure:\n'
                  '        _antlr_command = yield (False, _antlr_failure)\n'
                  '    else:\n        _antlr_command = yield (True, _antlr_result)\n')
        source += textwrap.indent(scope, '        ')
    if indices:
        source += '\n    _scopeMethods = {'+', '.join(f'{i}: _scope_{i}' for i in indices)+'}\n'
    return source
