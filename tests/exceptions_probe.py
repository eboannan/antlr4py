"""Observe action/exception lifecycle and nonlocal scopes in both generators."""
from antlr4 import CommonTokenStream, InputStream, ParseTreeListener
from antlr4.ParserRuleContext import ParserRuleContext
from antlr4.error.ErrorListener import ErrorListener


def snapshot(Lexer, Parser, case, *, generated=False):
    errors, callbacks = [], []
    class Errors(ErrorListener):
        def syntaxError(self, recognizer, token, line, column, message, error):
            errors.append([line, column, message, type(error).__name__ if error else None])
    class Recorder(ParseTreeListener):
        def enterEveryRule(self, ctx):
            callbacks.append(['enter', type(ctx).__name__])
        def exitEveryRule(self, ctx):
            callbacks.append(['exit', type(ctx).__name__, getattr(ctx, 'value', None),
                              list(parser.events)])
    kwargs = {'recover': True} if generated else {}
    parser = Parser(CommonTokenStream(Lexer(InputStream(case['input']))), **kwargs)
    parser.events, parser.mode, parser.limit = [], case.get('mode', 'ok'), case.get('limit', 100)
    parser.removeErrorListeners()
    parser.addErrorListener(Errors())
    parser.addParseListener(Recorder())
    tree, raised = None, None
    try:
        tree = getattr(parser, case.get('entry', 'start'))()
    except Exception as error:
        raised = [type(error).__name__, str(error)]
    contexts = []
    def record(ctx):
        contexts.append([type(ctx).__name__, getattr(ctx, 'value', None),
                         getattr(ctx, 'count', None), getattr(ctx, 'total', None),
                         type(ctx.exception).__name__ if ctx.exception else None,
                         list(ctx.getSourceInterval())])
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                record(child)
    if tree is not None:
        record(tree)
    return {'tree': tree.toStringTree(recog=parser) if tree is not None else None,
            'contexts': contexts, 'events': parser.events, 'callbacks': callbacks,
            'errors': errors, 'count': parser.getNumberOfSyntaxErrors(), 'raised': raised}
