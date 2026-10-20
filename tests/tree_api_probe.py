"""Behavioral snapshots shared by reference recording and Python-only tests."""
import inspect

from antlr4 import CommonTokenStream, InputStream, ParseTreeWalker
from antlr4.ParserRuleContext import ParserRuleContext


def node_value(value):
    if isinstance(value, list):
        return [node_value(node) for node in value]
    if value is None:
        return None
    return value.getText()


def snapshot(Lexer, Parser, Visitor, Listener, text):
    events = []
    class Recorder(Listener):
        def enterEveryRule(self, ctx):
            events.append(['enter', ctx.getRuleIndex(), type(ctx).__name__, ctx.getText()])

        def exitEveryRule(self, ctx):
            events.append(['exit', ctx.getRuleIndex(), type(ctx).__name__, ctx.getText()])

        def visitTerminal(self, node):
            events.append(['token', node.getText()])

    # Record rule-specific dispatch as well as generic walker/parse callbacks.
    for name in Parser.ruleNames:
        suffix = name[0].upper()+name[1:]
        for prefix in ('enter', 'exit'):
            def callback(self, ctx, method=prefix+suffix):
                events.append([method, ctx.getText()])
            setattr(Recorder, prefix+suffix, callback)

    parser = Parser(CommonTokenStream(Lexer(InputStream(text))))
    parser.addParseListener(Recorder())
    tree = parser.start()
    parsing = list(events)
    events.clear()
    ParseTreeWalker.DEFAULT.walk(Recorder(), tree)
    walking = list(events)

    counts = []
    class Counter(Visitor):
        pass
    for name in Parser.ruleNames:
        def visit(self, ctx, name=name):
            counts.append(name)
            return self.visitChildren(ctx)
        setattr(Counter, 'visit'+name[0].upper()+name[1:], visit)
    Counter().visit(tree)

    contexts = []
    def record(ctx):
        accessors = {}
        for name, method in type(ctx).__dict__.items():
            if not callable(method) or name not in set(Parser.ruleNames) | set(Parser.symbolicNames) | {'EOF'}:
                continue
            bound = getattr(ctx, name)
            parameters = inspect.signature(bound).parameters
            accessors[name] = {'list': 'i' in parameters, 'value': node_value(bound())}
            if 'i' in parameters:
                accessors[name]['first'] = node_value(bound(0))
                accessors[name]['missing'] = node_value(bound(999))
        contexts.append({'class': type(ctx).__name__, 'rule': ctx.getRuleIndex(),
                         'text': ctx.getText(), 'interval': list(ctx.getSourceInterval()),
                         'accessors': accessors})
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                record(child)
    record(tree)
    return {'tree': tree.toStringTree(recog=parser), 'contexts': contexts,
            'visitor_order': counts, 'walking': walking, 'parsing': parsing}
