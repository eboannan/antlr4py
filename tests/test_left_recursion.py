from pathlib import Path
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4.atn.ATNState import StarLoopEntryState
from antlr4.atn.Transition import PrecedencePredicateTransition, RuleTransition
from antlr4_generator import GrammarError, generate
from antlr4_generator.atn import build_atns
from antlr4_generator.grammar import read_grammar
from test_atn import load


class LeftRecursionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make(self, text):
        path = self.root / 'G.g4'
        path.write_text(text)
        lexer, parser = generate(path, self.root, overwrite=True)
        return getattr(load(lexer), lexer.stem), getattr(load(parser), parser.stem)

    def test_binary_precedence_and_left_associativity(self):
        Lexer, Parser = self.make("""grammar G;
            start: expr EOF;
            expr: expr '*' expr | expr '+' expr | INT;
            INT: [0-9]+;
        """)
        for text, expected in [
            ('2+3*4', '(start (expr (expr 2) + (expr (expr 3) * (expr 4))) <EOF>)'),
            ('2+3+4', '(start (expr (expr (expr 2) + (expr 3)) + (expr 4)) <EOF>)'),
        ]:
            parser = Parser(CommonTokenStream(Lexer(InputStream(text))))
            self.assertEqual(expected, parser.start().toStringTree(recog=parser))
            self.assertEqual([0], parser._precedenceStack)
            self.assertIsNone(parser._ctx)

    def test_right_associativity(self):
        Lexer, Parser = self.make("""grammar G; start: expr EOF;
            expr: <assoc=right> expr '^' expr | INT; INT: [0-9]+;
        """)
        parser = Parser(CommonTokenStream(Lexer(InputStream('2^3^4'))))
        self.assertEqual('(start (expr (expr 2) ^ (expr (expr 3) ^ (expr 4))) <EOF>)',
                         parser.start().toStringTree(recog=parser))

    def test_direct_entry_rule_and_precedence_argument(self):
        Lexer, Parser = self.make("grammar G; start: expr EOF; expr: expr '+' expr | INT; INT: [0-9]+;")
        parser = Parser(CommonTokenStream(Lexer(InputStream('1+2+3'))))
        self.assertEqual('(expr (expr (expr 1) + (expr 2)) + (expr 3))',
                         parser.expr().toStringTree(recog=parser))
        parser.reset()
        self.assertEqual('1', parser.expr(3).getText())
        self.assertEqual('+', parser.getCurrentToken().text)
        self.assertEqual([0], parser._precedenceStack)

    def test_recursive_only_grammar_matches_reference_eof_failure(self):
        # ANTLR 4.13.2 also reports no viable alternative at EOF for a recursive
        # rule without an entry-rule continuation. Retain fail-fast behavior.
        Lexer, Parser = self.make("grammar G; expr: expr '+' expr | INT; INT: [0-9]+;")
        parser = Parser(CommonTokenStream(Lexer(InputStream('1+2'))))
        with self.assertRaisesRegex(SyntaxError, 'viable alternative'):
            parser.expr()
        self.assertEqual([0], parser._precedenceStack)
        self.assertIsNone(parser._ctx)

    def test_error_unwinds_precedence_and_can_reset(self):
        Lexer, Parser = self.make("""grammar G; start: expr EOF;
            expr: '-' expr | expr '+' expr | '(' expr ')' | INT; INT: [0-9]+;
        """)
        parser = Parser(CommonTokenStream(Lexer(InputStream('1+'))))
        for text in ('1+', '1+(-2', '-@'):
            parser.setInputStream(CommonTokenStream(Lexer(InputStream(text))))
            with self.subTest(input=text), self.assertRaises(SyntaxError):
                parser.start()
            self.assertEqual([0], parser._precedenceStack)
            self.assertIsNone(parser._ctx)
        parser.setInputStream(CommonTokenStream(Lexer(InputStream('1+-2'))))
        self.assertEqual('1+-2<EOF>', parser.start().getText())

    def test_precedence_atn_metadata(self):
        grammar = read_grammar("grammar G; expr: expr '*' expr | expr '+' expr | INT; INT: [0-9]+;")
        self.assertEqual({'expr'}, grammar.left_recursive)
        _, atn = build_atns(grammar)
        self.assertTrue(atn.ruleToStartState[0].isPrecedenceRule)
        decisions = [s for s in atn.decisionToState
                     if isinstance(s, StarLoopEntryState) and s.isPrecedenceDecision]
        self.assertEqual(1, len(decisions))
        edges = [edge for state in atn.states for edge in state.transitions]
        self.assertEqual([3, 2], [e.precedence for e in edges
                                 if isinstance(e, PrecedencePredicateTransition)])
        self.assertEqual([4, 3], [e.precedence for e in edges if isinstance(e, RuleTransition)])

    def test_unsupported_recursion_and_options(self):
        for text in [
            "grammar G; expr: expr '+' expr;",  # no base case
            "grammar G; expr: expr;",
            "grammar G; expr: expr '+' expr | ;",  # nullable base
            "grammar G; expr: expr suffix | 'x'; suffix: ;",  # nullable suffix
            "grammar G; expr: other | expr '+' expr; other: expr;",  # indirect
            "grammar G; expr: (expr) '+' expr | 'x';",  # nested leading recursion
            "grammar G; expr: <assoc=sideways> expr '+' expr | 'x';",
            "grammar G; expr: <assoc=right> 'x';",
            "grammar G; expr: <assoc=right> expr '!' | 'x';",
            "grammar G; expr: expr '+' expr | <assoc=right> '-' expr | 'x';",
            "grammar G; expr: expr '+' expr | ('a' | <assoc=right> 'b');",
        ]:
            with self.subTest(grammar=text), self.assertRaises(GrammarError):
                read_grammar(text)


if __name__ == '__main__':
    unittest.main()
