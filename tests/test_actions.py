import json
from pathlib import Path
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4_generator import GrammarError, generate
from test_atn import load
from actions_probe import lexer_snapshot, parser_snapshot


FIXTURES = Path(__file__).with_name('fixtures')


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make(self, text):
        path = self.root / 'G.g4'
        path.write_text(text)
        lexer, parser = generate(path, self.root, overwrite=True)
        return load(lexer).GLexer, load(parser).GParser

    def fixture(self, name):
        paths = generate(FIXTURES / (name+'.g4'), self.root, overwrite=True)
        if len(paths) == 1:
            return getattr(load(paths[0]), name)
        return tuple(getattr(load(path), name+suffix) for path, suffix in zip(paths, ('Lexer', 'Parser')))

    def test_actions_compute_values_in_left_recursive_contexts(self):
        Lexer, Parser = self.fixture('Actions')
        parser = Parser(CommonTokenStream(Lexer(InputStream('2+3*4'))))
        tree = parser.start()
        self.assertEqual(14, tree.value)
        self.assertEqual([['integer', 2], ['integer', 3], ['integer', 4],
                          ['multiply', 12], ['add', 14], ['result', 14],
                          ['after', '2+3*4', '4']], parser.events)
        self.assertIsInstance(tree.result, Parser.AddContext)

    def test_python_locals_persist_between_actions_and_are_isolated_per_invocation(self):
        Lexer, Parser = self.make('''grammar G;
            start returns [value: int]
            @init {count = 0}
            @after {$value = count}
                : (item {count += 1})+ EOF;
            item: INT {temporary = int($INT.text)} {self.last = temporary};
            INT: [0-9]+; WS: ' ' -> skip;
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('1 2 3'))))
        for _ in range(2):
            parser.reset()
            self.assertEqual(3, parser.start().value)
            self.assertEqual(3, parser.last)

    def test_predicates_control_prediction_and_are_not_cached_as_booleans(self):
        Lexer, Parser = self.fixture('Predicates')
        parser = Parser(CommonTokenStream(Lexer(InputStream('42'))))
        for enabled, expected in [(True, 'enabled'), (False, 'fallback'), (True, 'enabled')]:
            parser.reset()
            parser.enabled = enabled
            self.assertEqual(expected, parser.start().selected)
        parser.reset()
        self.assertEqual(45, parser.guard(3).value)
        parser.reset()
        with self.assertRaisesRegex(SyntaxError, 'semantic predicate'):
            parser.guard(0)
        self.assertIsNone(parser._ctx)
        parser.reset()
        self.assertEqual(42, parser.checked().value)

    def test_lexer_actions_run_only_for_the_winning_token_and_at_correct_positions(self):
        Lexer = self.fixture('LexerActions')
        lexer = Lexer(InputStream('ab abc # abc def 12'))
        lexer.events, lexer.allow = [], False
        tokens = lexer.getAllTokens()
        self.assertEqual(['ab', 'abc', 'ABC', 'def', 'n:12'], [token.text for token in tokens])
        self.assertEqual([['middle', 'a', 1], ['pair', 'ab', 2], ['fallback', 'abc', 6],
                          ['mark', '#', 8], ['word', 'abc', 12], ['fallback', 'def', 16]], lexer.events)

    def test_strings_comments_braces_and_implicit_references(self):
        Lexer, Parser = self.make('''grammar G;
            start returns [value: int, data: dict]: child EOF {
                # $missing and } are Python comment text
                text = """} $missing {"""
                $data = {"literal": "$missing", "nested": {"text": text}}
                $value = $child.value
            };
            child returns [value: int]: INT {$value = $INT.int};
            INT: [0-9]+;
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('12'))))
        tree = parser.start()
        self.assertEqual(12, tree.value)
        self.assertEqual({'literal': '$missing', 'nested': {'text': '} $missing {'}}, tree.data)
        self.assertEqual(12, int(tree.child().INT().getText()))

    def test_actions_are_not_executed_during_prediction_or_generation(self):
        Lexer, Parser = self.make('''grammar G;
            start @init {self.events = []}: (first | second) EOF;
            first: 'a' {self.events.append('first')} 'b';
            second: 'a' {self.events.append('second')} 'c';
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('ac'))))
        parser.start()
        self.assertEqual(['second'], parser.events)
        Lexer, Parser = self.make("grammar G; start: 'x' {raise ValueError('from action')};")
        parser = Parser(CommonTokenStream(Lexer(InputStream('x'))))
        with self.assertRaisesRegex(ValueError, 'from action'):
            parser.start()
        self.assertIsNone(parser._ctx)
        self.assertEqual([0], parser._precedenceStack)

    def test_named_actions_and_literal_lexer_actions_survive_composition(self):
        (self.root / 'Base.g4').write_text('''grammar Base;
            @header {import math}
            @members {marker = 17}
            child returns [value: int]
            @init {self.entered = True}
                : INT {$value = math.floor(float($INT.text))};
            INT: [0-9]+;
        ''')
        Lexer, Parser = self.make('''grammar G; import Base;
            start returns [value: int]: child '+' EOF {$value = $child.value};
            PLUS: '+' {self.hit = self.marker};
        ''')
        lexer = Lexer(InputStream('12+'))
        parser = Parser(CommonTokenStream(lexer))
        self.assertEqual(12, parser.start().value)
        self.assertTrue(parser.entered)
        self.assertEqual(17, lexer.hit)
        self.assertEqual(17, parser.marker)
        self.assertEqual(Parser.PLUS, Lexer.PLUS)
        self.assertIn("'+'=", (self.root / 'G.tokens').read_text())

    def test_predicates_in_loops_and_after_actions(self):
        Lexer, Parser = self.make('''grammar G;
            start returns [value: int=0]: ({self.take}? INT {$value += 1})* INT EOF;
            checkRule returns [value: int=0]: INT {$value = 3} {$value == 3}?;
            INT: [0-9]+; WS: ' ' -> skip;
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('1 2 3'))))
        parser.take = True
        self.assertEqual(2, parser.start().value)
        parser.reset()
        parser.take = False
        with self.assertRaises(SyntaxError):
            parser.start()
        parser = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        self.assertEqual(3, parser.checkRule().value)

    def test_invalid_actions_leave_no_outputs(self):
        for text in [
            "grammar G; start: 'x' {$missing = 1};",
            "grammar G; start: 'x' {if};",
            "grammar G; start: {1 +}? 'x';",
            "grammar G; start: 'x' {$outer::value = 1};",
            "grammar G; @header {if} start: 'x';",
            "grammar G; @members {def broken(} start: 'x';",
            "grammar G; start: 'x' {unclosed;",
            "lexer grammar G; X: 'x' {$missing};",
            "grammar G; start: 'x' {yield 3};",
            "grammar G; start: {(yield 3)}? 'x';",
            "grammar G; start: {await f()}? 'x';",
        ]:
            with self.subTest(grammar=text):
                path = self.root / 'G.g4'
                path.write_text(text)
                output = self.root / 'bad'
                with self.assertRaises(GrammarError):
                    generate(path, output)
                self.assertFalse(output.exists())

    def test_reference_actions_and_predicates(self):
        reference = json.loads((FIXTURES / 'actions_reference.json').read_text())
        for name, cases in reference['grammars'].items():
            recognizers = self.fixture(name)
            for case in cases:
                with self.subTest(grammar=name, case=case['input'], entry=case.get('entry')):
                    actual = (lexer_snapshot(recognizers, case) if name == 'LexerActions' else
                              parser_snapshot(*recognizers, case))
                    self.assertEqual(case['snapshot'], actual)


if __name__ == '__main__':
    unittest.main()
