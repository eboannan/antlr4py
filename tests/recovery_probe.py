"""Compare observable recovery behavior without depending on ATN state numbers."""
from antlr4 import CommonTokenStream, InputStream, ParseTreeListener, ParseTreeWalker
from antlr4.ParserRuleContext import ParserRuleContext
from antlr4.Token import Token
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Tree import ErrorNode


def snapshot(Lexer, Parser, case, *, generated=False):
    errors, lex_errors, callbacks = [], [], []
    class Errors(ErrorListener):
        def __init__(self, target):
            self.target = target
        def syntaxError(self, recognizer, token, line, column, message, error):
            self.target.append([line, column, message, token.text if token else None,
                                type(error).__name__ if error else None])
    def value(item):
        if isinstance(item, list):
            return [value(child) for child in item]
        if isinstance(item, Token):
            return [item.text, item.type, item.tokenIndex]
        if isinstance(item, ParserRuleContext):
            return [type(item).__name__, item.getText()]
        return item
    def fields(ctx):
        return {name: value(getattr(ctx, name)) for name in
                ('name', 'result', 'left', 'right', 'inner', 'number', 'values', 'chosen')
                if hasattr(ctx, name)}
    class Recorder(ParseTreeListener):
        def enterEveryRule(self, ctx):
            callbacks.append(['enter', type(ctx).__name__, fields(ctx)])
        def exitEveryRule(self, ctx):
            callbacks.append(['exit', type(ctx).__name__, fields(ctx)])
        def visitTerminal(self, node):
            callbacks.append(['token', node.getText(), fields(node.parentCtx)])
        def visitErrorNode(self, node):
            callbacks.append(['error', node.getText(), fields(node.parentCtx)])
    kwargs = {'recover': True} if generated else {}
    lexer = Lexer(InputStream(case['input']), **kwargs)
    lexer.removeErrorListeners()
    lexer.addErrorListener(Errors(lex_errors))
    parser = Parser(CommonTokenStream(lexer), **kwargs)
    parser.allowed = case.get('allowed', False)
    parser.removeErrorListeners()
    parser.addErrorListener(Errors(errors))
    parser.addParseListener(Recorder())
    tree = getattr(parser, case.get('entry', 'start'))()
    parsing = list(callbacks)
    callbacks.clear()
    ParseTreeWalker.DEFAULT.walk(Recorder(), tree)
    contexts, nodes = [], []
    def record(ctx):
        contexts.append([type(ctx).__name__, fields(ctx), list(ctx.getSourceInterval()),
                         type(ctx.exception).__name__ if ctx.exception else None])
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                record(child)
            else:
                nodes.append([child.getText(), isinstance(child, ErrorNode), child.symbol.tokenIndex])
    record(tree)
    return {'tree': tree.toStringTree(recog=parser), 'errors': errors, 'lex_errors': lex_errors,
            'count': parser.getNumberOfSyntaxErrors(), 'contexts': contexts, 'nodes': nodes,
            'parsing': parsing, 'walking': callbacks, 'index': parser._input.index,
            'finished': getattr(parser, 'finished', False)}
