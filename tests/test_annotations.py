import json
from pathlib import Path
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream, ParseTreeWalker
from antlr4_generator import GrammarError, generate
from test_atn import load
from annotations_probe import snapshot


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make(self, text):
        path = self.root / 'G.g4'
        path.write_text(text)
        lexer, parser = generate(path, self.root, visitor=True, overwrite=True)
        return load(lexer).GLexer, load(parser).GParser

    def test_labeled_expression_contexts_and_evaluator(self):
        fixtures = Path(__file__).with_name('fixtures')
        lexer, parser = generate(fixtures / 'Labels.g4', self.root, visitor=True)
        Lexer, Parser = load(lexer).LabelsLexer, load(parser).LabelsParser
        Visitor = load(self.root / 'LabelsVisitor.py').LabelsVisitor
        class Evaluate(Visitor):
            def visitStart(self, ctx):
                return [self.visit(value) for value in ctx.values]
            def visitMultiply(self, ctx):
                return self.visit(ctx.left)*self.visit(ctx.right)
            def visitAdd(self, ctx):
                return self.visit(ctx.left)+self.visit(ctx.right)
            def visitInteger(self, ctx):
                return int(ctx.value.text)
            def visitParentheses(self, ctx):
                return self.visit(ctx.inner)
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('2+3*4,(2+3)*4'))))
        tree = recognizer.start()
        self.assertEqual([14, 20], Evaluate().visit(tree))
        self.assertIsInstance(tree.values[0], Parser.AddContext)
        self.assertIsInstance(tree.values[0], Parser.ExprContext)
        self.assertIsInstance(tree.values[0].right, Parser.MultiplyContext)
        self.assertEqual('+', tree.values[0].op.text)
        self.assertIs(tree.values[0].left.parentCtx, tree.values[0])
        self.assertFalse(hasattr(Visitor, 'visitExpr'))

    def test_scalar_and_list_labels_without_tree_storage(self):
        Lexer, Parser = self.make('grammar G; start: first=item (others+=item)* last=EOF; item: token=INT; INT: [0-9]+; WS: \' \' -> skip;')
        parser = Parser(CommonTokenStream(Lexer(InputStream('1 2 3'))))
        parser.buildParseTrees = False
        tree = parser.start()
        self.assertEqual('1', tree.first.token.text)
        self.assertEqual(['2', '3'], [ctx.token.text for ctx in tree.others])
        self.assertEqual('<EOF>', tree.last.text)

    def test_rule_arguments_returns_locals_and_forwarding(self):
        Lexer, Parser = self.make('''grammar G;
            start: result=parentRule[3] EOF;
            parentRule[n: int] returns [result: int=0]: childRule[$n+1];
            childRule[n: int] returns [value: int=7] locals [seen: list=[]]: token=INT;
            INT: [0-9]+;
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('42'))))
        tree = parser.start()
        child = tree.result.childRule()
        self.assertEqual((3, 4, 0, 7, []), (tree.result.n, child.n, tree.result.result, child.value, child.seen))
        parser.reset()
        first = parser.childRule(10)
        first.seen.append(1)
        parser.reset()
        second = parser.childRule(n=20)
        self.assertEqual((20, []), (second.n, second.seen))

    def test_shared_alt_label_and_token_set_labels(self):
        Lexer, Parser = self.make("grammar G; start: expr EOF; expr: sign=('+'|'-') number=INT # Signed | number=INT # Signed; INT: [0-9]+;")
        for text, sign in [('12', None), ('-12', '-')]:
            parser = Parser(CommonTokenStream(Lexer(InputStream(text))))
            ctx = parser.start().expr()
            self.assertIsInstance(ctx, Parser.SignedContext)
            self.assertEqual(sign, ctx.sign.text if ctx.sign else None)
            self.assertEqual('12', ctx.number.text)

    def test_attribute_literals_and_default_arguments(self):
        Lexer, Parser = self.make("grammar G; start: child EOF; child[n: int=5] locals [data: list=[1,2], text: str=']']: INT; INT: [0-9]+;")
        parser = Parser(CommonTokenStream(Lexer(InputStream('8'))))
        ctx = parser.start().child()
        self.assertEqual((5, [1, 2], ']'), (ctx.n, ctx.data, ctx.text))

    def test_invalid_annotations(self):
        cases = [
            'grammar G; start: INT # One | INT;',
            'grammar G; start: INT # Start;',
            'grammar G; start: child EOF; child[n: int]: INT; INT: [0-9]+;',
            'grammar G; start: child[1,2] EOF; child[n: int]: INT; INT: [0-9]+;',
            'grammar G; start: child[$missing] EOF; child[n: int]: INT; INT: [0-9]+;',
            'grammar G; start: child[1 +] EOF; child[n: int]: INT; INT: [0-9]+;',
            'grammar G; start: xs=(INT INT); INT: [0-9]+;',
            'grammar G; start: x=INT x+=INT; INT: [0-9]+;',
            'grammar G; start: INT; returnsRule returns [x=1 +]: INT; INT: [0-9]+;',
            'grammar G; start: INT; child[x=1,y]: INT; INT: [0-9]+;',
            'grammar G; start: INT; child[self: int]: INT; INT: [0-9]+;',
        ]
        for text in cases:
            path = self.root / 'G.g4'
            path.write_text(text)
            output = self.root / 'bad'
            with self.subTest(grammar=text), self.assertRaises(GrammarError):
                generate(path, output)
            self.assertFalse(output.exists())

    def test_reference_fields_and_listener_timing(self):
        fixtures = Path(__file__).with_name('fixtures')
        reference = json.loads((fixtures / 'annotations_reference.json').read_text())
        for name, data in reference['grammars'].items():
            lexer, parser = generate(fixtures / (name+'.g4'), self.root, visitor=True)
            Lexer, Parser = getattr(load(lexer), name+'Lexer'), getattr(load(parser), name+'Parser')
            Visitor = getattr(load(self.root / (name+'Visitor.py')), name+'Visitor')
            Listener = getattr(load(self.root / (name+'Listener.py')), name+'Listener')
            for case in data['cases']:
                with self.subTest(grammar=name, text=case['input']):
                    self.assertEqual(case['snapshot'], snapshot(
                        Lexer, Parser, Visitor, Listener, case['input'], data['fields']))


if __name__ == '__main__':
    unittest.main()
