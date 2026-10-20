"""Record labeled contexts, fields, and listener timing for compatibility tests."""
from antlr4 import CommonTokenStream, InputStream, ParseTreeWalker
from antlr4.ParserRuleContext import ParserRuleContext
from antlr4.Token import Token


def value(item):
    if isinstance(item, list):
        return [value(child) for child in item]
    if isinstance(item, ParserRuleContext):
        return {'context': type(item).__name__, 'text': item.getText()}
    if isinstance(item, Token):
        return {'token': item.text, 'type': item.type, 'index': item.tokenIndex}
    return item


def snapshot(Lexer, Parser, Visitor, Listener, text, fields):
    events = []
    def attributes(ctx):
        return {name: value(getattr(ctx, name)) for name in fields if hasattr(ctx, name)}
    class Recorder(Listener):
        def enterEveryRule(self, ctx):
            events.append(['enter', type(ctx).__name__, attributes(ctx)])
        def exitEveryRule(self, ctx):
            events.append(['exit', type(ctx).__name__, attributes(ctx)])
        def visitTerminal(self, node):
            events.append(['token', node.getText(), attributes(node.parentCtx)])
    for name in Listener.__dict__:
        if name.startswith(('enter', 'exit')):
            def event(self, ctx, name=name):
                events.append([name, attributes(ctx)])
            setattr(Recorder, name, event)
    parser = Parser(CommonTokenStream(Lexer(InputStream(text))))
    parser.addParseListener(Recorder())
    tree = parser.start()
    parsing = list(events)
    events.clear()
    ParseTreeWalker.DEFAULT.walk(Recorder(), tree)
    walking = list(events)
    visited = []
    class Visits(Visitor):
        pass
    for name in Visitor.__dict__:
        if name.startswith('visit'):
            def visit(self, ctx, name=name):
                visited.append(name)
                return self.visitChildren(ctx)
            setattr(Visits, name, visit)
    Visits().visit(tree)
    contexts = []
    def record(ctx):
        contexts.append({'class': type(ctx).__name__, 'fields': attributes(ctx),
                         'rule': ctx.getRuleIndex(), 'text': ctx.getText(),
                         'interval': list(ctx.getSourceInterval())})
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                record(child)
    record(tree)
    return {'tree': tree.toStringTree(recog=parser), 'contexts': contexts,
            'visits': visited, 'walking': walking, 'parsing': parsing}
