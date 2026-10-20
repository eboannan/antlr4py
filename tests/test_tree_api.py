import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream, ParseTreeVisitor, ParseTreeWalker
from antlr4_generator import GrammarError, generate
from test_atn import load
from tree_api_probe import snapshot


class TreeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make(self, text, **options):
        path = self.root / 'G.g4'
        path.write_text(text)
        lexer_path, parser_path = generate(path, self.root, overwrite=True, **options)
        return getattr(load(lexer_path), lexer_path.stem), getattr(load(parser_path), parser_path.stem)

    def test_typed_contexts_accessors_and_visitor_evaluation(self):
        fixtures = Path(__file__).with_name('fixtures')
        lexer_path, parser_path = generate(fixtures / 'TreeApi.g4', self.root, visitor=True)
        Lexer, Parser = load(lexer_path).TreeApiLexer, load(parser_path).TreeApiParser
        Visitor = load(self.root / 'TreeApiVisitor.py').TreeApiVisitor
        class Evaluate(Visitor):
            def visitStart(self, ctx):
                return [self.visit(expr) for expr in ctx.expr()]

            def visitExpr(self, ctx):
                if ctx.INT():
                    return int(ctx.INT().getText())
                operands = ctx.expr()
                if len(operands) == 1:
                    return self.visit(operands[0])
                left, right = (self.visit(node) for node in operands)
                return left*right if ctx.getChild(1).getText() == '*' else left+right
        parser = Parser(CommonTokenStream(Lexer(InputStream('2+3*4,(2+3)*4'))))
        tree = parser.start()
        self.assertIsInstance(tree, Parser.StartContext)
        self.assertIsInstance(tree.expr(0), Parser.ExprContext)
        self.assertEqual(Parser.RULE_start, tree.getRuleIndex())
        self.assertEqual([14, 20], Evaluate().visit(tree))
        self.assertEqual('<EOF>', tree.EOF().getText())
        self.assertIsNone(tree.expr(100))

    def test_visitor_fallback_and_tree_building_disabled(self):
        Lexer, Parser = self.make('grammar G; start: item EOF; item: INT; INT: [0-9]+;')
        class Generic(ParseTreeVisitor):
            def visitTerminal(self, node):
                return node.getText()
        parser = Parser(CommonTokenStream(Lexer(InputStream('12'))))
        tree = parser.start()
        self.assertEqual('12', Generic().visit(tree.item()))
        self.assertIsInstance(tree.item(), Parser.ItemContext)
        parser.reset()
        parser.buildParseTrees = False
        tree = parser.start()
        self.assertIsNone(tree.item())
        self.assertEqual([], list(tree.getChildren()))

    def test_context_names_do_not_shadow_the_runtime_base(self):
        Lexer, Parser = self.make('grammar G; rule: item EOF; item: INT; INT: [0-9]+;')
        parser = Parser(CommonTokenStream(Lexer(InputStream('42'))))
        tree = parser.rule_()
        self.assertIsInstance(tree, Parser.RuleContext)
        self.assertIsInstance(tree.item(), Parser.ItemContext)
        self.assertEqual('42', tree.item().INT().getText())

    def test_reference_contexts_visitors_and_listener_events(self):
        fixtures = Path(__file__).with_name('fixtures')
        reference = json.loads((fixtures / 'tree_api_reference.json').read_text())
        for name, cases in reference['grammars'].items():
            lexer, parser = generate(fixtures / (name+'.g4'), self.root, visitor=True)
            Lexer, Parser = getattr(load(lexer), name+'Lexer'), getattr(load(parser), name+'Parser')
            Visitor = getattr(load(self.root / (name+'Visitor.py')), name+'Visitor')
            Listener = getattr(load(self.root / (name+'Listener.py')), name+'Listener')
            for case in cases:
                with self.subTest(grammar=name, text=case['input']):
                    self.assertEqual(case['snapshot'], snapshot(Lexer, Parser, Visitor, Listener, case['input']))

    def test_flags_and_protect_helper_files(self):
        Lexer, Parser = self.make("grammar G; start: 'a' EOF;", visitor=True)
        self.assertTrue((self.root / 'GVisitor.py').exists())
        self.assertTrue((self.root / 'GListener.py').exists())
        output = self.root / 'off'
        generate(self.root / 'G.g4', output, listener=False)
        self.assertFalse((output / 'GListener.py').exists())
        self.assertFalse((output / 'GVisitor.py').exists())
        output = self.root / 'collision'
        output.mkdir()
        (output / 'GVisitor.py').write_text('user code')
        with self.assertRaises(FileExistsError):
            generate(self.root / 'G.g4', output, visitor=True)
        self.assertFalse((output / 'GParser.py').exists())
        result = subprocess.run([sys.executable, '-m', 'antlr4_generator', str(self.root / 'G.g4'),
                                 '-visitor', '-no-listener', '-o', str(self.root / 'cli')],
                                env=dict(os.environ, PATH=str(self.root / 'no-tools')),
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.root / 'cli/GVisitor.py').exists())
        self.assertFalse((self.root / 'cli/GListener.py').exists())

    def test_conflicting_context_names_fail_before_output(self):
        for text in [
            'grammar G; expr: INT; ExprContext: \'x\'; INT: [0-9]+;',
            'grammar G; outer: start; start: INT; INT: [0-9]+;',
        ]:
            path = self.root / 'G.g4'
            path.write_text(text)
            output = self.root / 'bad'
            with self.assertRaises(GrammarError):
                generate(path, output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
