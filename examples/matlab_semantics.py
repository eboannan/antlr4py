"""A closed-world name/definite-assignment check over AST nodes only.

This is a teaching analyzer, not MATLAB type inference or workspace execution.
"""
from dataclasses import dataclass


FUNCTIONS = frozenset({'sin', 'cos', 'feval', 'disp', 'length', 'size', 'sum', 'zeros', 'ones', 'isempty'})
CONSTANTS = frozenset({'pi', 'i', 'j', 'Inf', 'NaN', 'inf', 'nan', 'eps'})
WORKSPACE_EFFECTS = frozenset({'load', 'clear', 'eval', 'evalin', 'assignin'})


@dataclass
class Diagnostic:
    code: str
    message: str
    line: int
    column: int

    def __str__(self):
        return f'{self.line}:{self.column}: {self.code}: {self.message}'


class SemanticAnalyzer:
    def __init__(self, *, functions=FUNCTIONS):
        self.functions = set(functions)
        self.diagnostics = []
        self.defined = set()
        self.possible = set()

    def report(self, node, code, message):
        self.diagnostics.append(Diagnostic(code, message, node.line, node.column))

    def analyze(self, program):
        self.diagnostics = []
        self.defined = set()
        self.possible = set()
        self.statements(program.children)
        return self.diagnostics

    def statements(self, statements):
        for node in statements:
            if node.kind == 'Assign':
                target, value = node.children
                self.expression(value)  # RHS is checked before introducing the target.
                self.defined.add(target.value)
                self.possible.add(target.value)
            elif node.kind == 'If':
                self.conditional(node)
            elif node.kind == 'Command':
                self.check_function(node, node.value)
                # Command arguments are literal text, not variable references.
            elif node.kind == 'ExpressionStatement':
                self.expression(node.children[0])
            else:
                raise ValueError(f'unsupported semantic statement: {node.kind}')

    def check_function(self, node, name):
        if name in WORKSPACE_EFFECTS:
            self.report(node, 'UNSUPPORTED_WORKSPACE_EFFECT',
                        f"'{name}' changes workspace bindings dynamically")
        elif name not in self.functions:
            self.report(node, 'UNKNOWN_FUNCTION', f"function '{name}' is not in the demo's function catalog")

    def expression(self, node):
        if node.kind == 'Name':
            if node.value in self.defined:
                return
            if node.value in self.possible:
                self.report(node, 'POSSIBLY_UNASSIGNED', f"'{node.value}' is not assigned on every path")
            elif node.value not in self.functions and node.value not in CONSTANTS:
                self.report(node, 'UNDEFINED_NAME', f"'{node.value}' is not defined or in the demo's catalog")
        elif node.kind == 'Handle':
            self.check_function(node, node.value)
        elif node.kind == 'Apply' and node.children[0].kind == 'Name' and node.children[0].value in WORKSPACE_EFFECTS:
            self.check_function(node.children[0], node.children[0].value)
            for argument in node.children[1:]:
                self.expression(argument)
        else:
            for child in node.children:
                self.expression(child)

    def conditional(self, node):
        incoming = (set(self.defined), set(self.possible))
        outcomes = []
        has_else = False
        for branch in node.children:
            self.defined, self.possible = map(set, incoming)
            body = branch.children
            if branch.kind == 'Branch':
                self.expression(body[0])
                body = body[1:]
            else:
                has_else = True
            self.statements(body)
            outcomes.append((set(self.defined), set(self.possible)))
        if not has_else:
            outcomes.append(incoming)
        self.defined = set.intersection(*(defined for defined, _ in outcomes))
        self.possible = set.union(*(possible for _, possible in outcomes))
