"""Record semantic values, action side effects, and live listener ordering."""
from antlr4 import CommonTokenStream, InputStream, ParseTreeListener
from antlr4.ParserRuleContext import ParserRuleContext


def parser_snapshot(Lexer, Parser, case):
    events = []
    class Recorder(ParseTreeListener):
        def enterEveryRule(self, ctx):
            events.append(['enter', type(ctx).__name__, getattr(ctx, 'value', None)])
        def exitEveryRule(self, ctx):
            events.append(['exit', type(ctx).__name__, getattr(ctx, 'value', None)])
    lexer = Lexer(InputStream(case['input']))
    parser = Parser(CommonTokenStream(lexer))
    parser.enabled = case.get('enabled', False)
    parser.addParseListener(Recorder())
    tree = getattr(parser, case.get('entry', 'start'))(*case.get('arguments', []))
    contexts = []
    def record(ctx):
        contexts.append([type(ctx).__name__, getattr(ctx, 'value', None),
                         getattr(ctx, 'selected', None), list(ctx.getSourceInterval())])
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                record(child)
    record(tree)
    return {'tree': tree.toStringTree(recog=parser), 'contexts': contexts,
            'callbacks': events, 'events': getattr(parser, 'events', []),
            'summary': getattr(parser, 'summary', None), 'last': getattr(parser, 'last', None),
            'literal_actions': getattr(lexer, 'plusCount', 0)}


def lexer_snapshot(Lexer, case):
    lexer = Lexer(InputStream(case['input']))
    lexer.events, lexer.allow = [], case.get('allow', False)
    tokens = lexer.getAllTokens()
    return {'tokens': [[token.type, token.text, token.channel, token.start, token.stop,
                        token.line, token.column] for token in tokens],
            'events': lexer.events, 'allow': lexer.allow}
