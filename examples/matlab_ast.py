"""A deliberately small AST builder for MATLAB scripts, independent of execution."""
from dataclasses import asdict, dataclass, field

from antlr4.tree.Tree import TerminalNode
from generated.matlab61Visitor import matlab61Visitor


@dataclass
class Node:
    kind: str
    value: str | None = None
    children: list['Node'] = field(default_factory=list)
    line: int = 1
    column: int = 1

    def to_dict(self):
        return asdict(self)


class UnsupportedSyntax(ValueError):
    """Valid grammar syntax outside this teaching example's AST subset."""


class AstBuilder(matlab61Visitor):
    def node(self, kind, ctx, children=(), value=None):
        return Node(kind, value, list(children), ctx.start.line, ctx.start.column + 1)

    def unsupported(self, ctx, message):
        raise UnsupportedSyntax(f'{ctx.start.line}:{ctx.start.column + 1}: {message}')

    def visitChildren(self, ctx):
        self.unsupported(ctx, f'unsupported AST rule: {type(ctx).__name__}')

    def visitFile_(self, ctx):
        if ctx.function_file():
            self.unsupported(ctx, 'function files are outside this AST example')
        statements = self.visit(ctx.script_file()) if ctx.script_file() else []
        return self.node('Program', ctx, statements)

    def visitScript_file(self, ctx):
        return [self.visit(statement) for statement in ctx.statement()]

    def visitBlock(self, ctx):
        return [self.visit(statement) for statement in ctx.statement()]

    def visitStatement(self, ctx):
        if ctx.assignment_expression():
            return self.visit(ctx.assignment_expression())
        if ctx.command_statement():
            return self.visit(ctx.command_statement())
        if ctx.IF():
            branches = []
            for condition, block in zip(ctx.expression(), ctx.block()):
                branches.append(self.node('Branch', block,
                                          [self.visit(condition), *self.visit(block)]))
            if ctx.ELSE():
                block = ctx.block()[-1]
                branches.append(self.node('Else', block, self.visit(block)))
            return self.node('If', ctx, branches)
        # Control/declaration rules have other leading terminals; fail explicitly.
        if ctx.expression() and type(ctx.children[0]).__name__ == 'ExpressionContext':
            return self.node('ExpressionStatement', ctx, [self.visit(ctx.expression(0))])
        self.unsupported(ctx, 'only assignments, expressions, commands and if/elseif/else are supported')

    def visitAssignment_expression(self, ctx):
        target = ctx.assignment_target()
        if target.IDENTIFIER() is None or target.postfix_suffix():
            self.unsupported(target, 'only a single plain-name assignment target is supported')
        name = self.node('Name', target, value=target.IDENTIFIER().getText())
        return self.node('Assign', ctx, [name, self.visit(ctx.expression())])

    def visitCommand_statement(self, ctx):
        arguments = [Node('CommandArgument', token.getText(), [], token.symbol.line,
                          token.symbol.column + 1) for token in ctx.COMMAND_ARGUMENT()]
        return self.node('Command', ctx, arguments, ctx.IDENTIFIER().getText())

    def visitExpression(self, ctx):
        return self.visit(ctx.or_expression())

    def fold_binary(self, ctx):
        result = self.visit(ctx.children[0])
        for operator, operand in zip(ctx.children[1::2], ctx.children[2::2]):
            result = self.node('Binary', ctx, [result, self.visit(operand)], operator.getText())
        return result

    visitOr_expression = fold_binary
    visitAnd_expression = fold_binary
    visitRelational_expression = fold_binary
    visitAdditive_expression = fold_binary
    visitMultiplicative_expression = fold_binary
    visitPower_expression = fold_binary

    def visitColon_expression(self, ctx):
        operands = [self.visit(child) for child in ctx.additive_expression()]
        return operands[0] if len(operands) == 1 else self.node('Range', ctx, operands)

    def visitUnary_expression(self, ctx):
        if ctx.power_expression():
            return self.visit(ctx.power_expression())
        return self.node('Unary', ctx, [self.visit(ctx.unary_expression())], ctx.children[0].getText())

    def visitSigned_postfix(self, ctx):
        result = self.visit(ctx.postfix_expression())
        for operator in reversed(ctx.children[:-1]):
            result = self.node('Unary', ctx, [result], operator.getText())
        return result

    def visitPostfix_expression(self, ctx):
        result = self.visit(ctx.primary_expression())
        for suffix in ctx.children[1:]:
            if isinstance(suffix, TerminalNode):
                result = self.node('Unary', ctx, [result], suffix.getText())
            elif suffix.DOT():
                result = self.node('Field', suffix, [result], suffix.IDENTIFIER().getText())
            else:
                arguments = suffix.index_expression_list()
                items = [self.visit(item) for item in arguments.index_expression()] if arguments else []
                kind = 'Apply' if suffix.LPAREN() else 'CellIndex'
                # Parentheses may mean a function call or array indexing in MATLAB.
                result = self.node(kind, ctx, [result, *items])
        return result

    def visitIndex_expression(self, ctx):
        if ctx.COLON():
            return self.node('AllIndices', ctx)
        return self.visit(ctx.expression())

    def visitPrimary_expression(self, ctx):
        if ctx.AT():
            return self.node('Handle', ctx, value=ctx.IDENTIFIER().getText())
        for accessor, kind in ((ctx.IDENTIFIER, 'Name'), (ctx.CONSTANT, 'Number'),
                               (ctx.STRING_LITERAL, 'String')):
            token = accessor()
            if token is not None:
                text = token.getText()
                if kind == 'String':
                    text = text[1:-1].replace("''", "'")
                return self.node(kind, ctx, value=text)
        if ctx.END_INDEX():
            return self.node('EndIndex', ctx)
        if ctx.expression():
            return self.visit(ctx.expression())
        rows = ctx.array_rows()
        children = [self.node('Row', row, [self.visit(item) for item in row.expression()])
                    for row in rows.array_row()] if rows else []
        return self.node('Matrix' if ctx.LBRACK() else 'Cell', ctx, children)
