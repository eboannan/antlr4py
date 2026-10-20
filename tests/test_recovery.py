import json
from pathlib import Path
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream, ParseTreeListener
from antlr4.error.ErrorStrategy import BailErrorStrategy, DefaultErrorStrategy
from antlr4.error.Errors import ParseCancellationException
from antlr4_generator import generate
from test_atn import load
from recovery_probe import snapshot


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixtures = Path(__file__).with_name('fixtures')
        lexer, parser = generate(fixtures / 'Recovery.g4', self.root)
        self.Lexer = load(lexer).RecoveryLexer
        self.Parser = load(parser).RecoveryParser

    def parser(self, text, **kwargs):
        return self.Parser(CommonTokenStream(self.Lexer(InputStream(text))), **kwargs)

    def test_reference_recovery(self):
        fixtures = Path(__file__).with_name('fixtures')
        reference = json.loads((fixtures / 'recovery_reference.json').read_text())
        for case in reference['cases']:
            with self.subTest(entry=case['entry'], text=case['input'], allowed=case.get('allowed')):
                self.assertEqual(case['snapshot'], snapshot(self.Lexer, self.Parser, case, generated=True))

    def test_strict_mode_remains_default_and_strategy_can_be_replaced(self):
        parser = self.parser('x 1;')
        with self.assertRaises(SyntaxError):
            parser.single()
        parser.reset()
        parser.removeErrorListeners()
        parser._errHandler = DefaultErrorStrategy()
        tree = parser.single()
        self.assertEqual(1, parser.getNumberOfSyntaxErrors())
        self.assertIn("<missing '='>", tree.getText())
        self.assertEqual('1', tree.number.text)

    def test_bail_strategy_marks_active_contexts_and_unwinds(self):
        parser = self.parser('x=(1+);', recover=True)
        parser.removeErrorListeners()
        parser._errHandler = BailErrorStrategy()
        entered, exited = [], []
        class Recorder(ParseTreeListener):
            def enterEveryRule(self, ctx):
                entered.append(ctx)
            def exitEveryRule(self, ctx):
                exited.append(ctx)
        parser.addParseListener(Recorder())
        with self.assertRaises(ParseCancellationException) as raised:
            parser.start()
        error = raised.exception.args[0]
        self.assertIsNotNone(error.ctx.exception)
        self.assertEqual(len(entered), len(exited))
        self.assertIs(exited[-1].exception, error)
        self.assertTrue(any(ctx.exception is error for ctx in exited))
        self.assertIsNone(parser._ctx)
        self.assertEqual([0], parser._precedenceStack)

    def test_reset_clears_recovery_state_and_error_count(self):
        parser = self.parser('x 1;', recover=True)
        parser.removeErrorListeners()
        for _ in range(2):
            parser.reset()
            self.assertEqual(0, parser.getNumberOfSyntaxErrors())
            parser.single()
            self.assertEqual(1, parser.getNumberOfSyntaxErrors())
            self.assertIsNone(parser._ctx)
            self.assertEqual([0], parser._precedenceStack)

    def test_missing_token_labels_without_tree_storage_and_after_hook_recovery(self):
        parser = self.parser('=1;', recover=True)
        parser.removeErrorListeners()
        parser.buildParseTrees = False
        tree = parser.single()
        self.assertEqual(self.Parser.ID, tree.name.type)
        self.assertTrue(tree.name.text.startswith('<missing '))
        self.assertEqual(-1, tree.name.tokenIndex)
        self.assertEqual('1', tree.number.text)
        self.assertIsNone(tree.children)
        self.assertEqual(1, parser.getNumberOfSyntaxErrors())
        parser = self.parser('1', recover=True)
        parser.allowed = True
        parser.removeErrorListeners()
        tree = parser.guard()
        self.assertTrue(parser.finished)
        self.assertIsNone(tree.exception)
        self.assertEqual(1, parser.getNumberOfSyntaxErrors())


if __name__ == '__main__':
    unittest.main()
