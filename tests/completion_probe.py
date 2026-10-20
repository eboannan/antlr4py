"""Compatibility snapshots for the remaining Python-target milestones."""
from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener
from antlr4.Token import Token


def snapshot(Lexer, Parser, case, *, generated=False):
    errors = []
    class Errors(ErrorListener):
        def syntaxError(self, recognizer, token, line, column, message, error):
            errors.append([line, column, message])
    lexer = Lexer(InputStream(case['input']), **({'recover': True} if generated else {}))
    lexer.removeErrorListeners()
    lexer.addErrorListener(Errors())
    stream = CommonTokenStream(lexer)
    tree, result, raised = None, None, None
    parser = None
    try:
        if Parser is not None:
            parser = Parser(stream, **({'recover': True} if generated else {}))
            parser.removeErrorListeners()
            parser.addErrorListener(Errors())
            tree = getattr(parser, case.get('entry', 'start'))()
            result = getattr(tree, 'value', None)
            if isinstance(result, Token):
                result = [result.text, result.type, result.tokenIndex]
        stream.fill()
    except Exception as error:
        raised = [type(error).__name__, str(error)]
    return {'tokens': [[token.type, token.text, token.channel, token.line, token.column,
                        token.start, token.stop] for token in stream.tokens],
            'tree': tree.toStringTree(recog=parser) if tree is not None else None,
            'value': result, 'errors': errors, 'raised': raised}
