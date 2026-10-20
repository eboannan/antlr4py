import json
from pathlib import Path
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4_generator import GrammarError, generate
from test_atn import load
from exceptions_probe import snapshot


FIXTURES = Path(__file__).with_name('fixtures')


class ExceptionTests(unittest.TestCase):
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
        return tuple(getattr(load(path), name+suffix) for path, suffix in zip(paths, ('Lexer', 'Parser')))

    def test_catches_replace_default_handler_and_finally_precedes_exit(self):
        Lexer, Parser = self.fixture('Exceptions')
        for mode, expected in [('ok', 12), ('value', 5), ('key', -1), ('runtime', None)]:
            parser = Parser(CommonTokenStream(Lexer(InputStream('12'))))
            parser.events, parser.mode = [], mode
            tree = parser.start()
            self.assertEqual(expected, tree.value)
            self.assertIsNone(parser._ctx)
            self.assertEqual(0, parser.getNumberOfSyntaxErrors())
            self.assertEqual(['finallyStart', 10, expected], parser.events[-1])
            if mode == 'ok':
                self.assertEqual('afterChild', parser.events[0][0])
            else:
                self.assertNotIn('afterChild', [event[0] for event in parser.events])

    def test_nonlocal_reads_writes_predicates_and_arguments(self):
        Lexer, Parser = self.fixture('Nonlocals')
        parser = Parser(CommonTokenStream(Lexer(InputStream('(1 (2 3) 4)'))))
        parser.events, parser.limit = [], 100
        tree = parser.start()
        self.assertEqual((10, 4), (tree.value, tree.count))
        self.assertEqual([['argument', 1], ['argument', 2], ['argument', 5], ['argument', 10]],
                         [event for event in parser.events if event[0] == 'argument'])
        self.assertEqual(['finallyStart', 4], parser.events[-1])

    def test_catch_reraise_and_finally_exception_unwind(self):
        Lexer, Parser = self.fixture('Exceptions')
        parser = Parser(CommonTokenStream(Lexer(InputStream('12'))))
        parser.events, parser.mode = [], 'runtime'
        with self.assertRaisesRegex(RuntimeError, 'bubble up'):
            parser.reraised()
        self.assertEqual(['finallyReraised'], parser.events[-1])
        self.assertIsNone(parser._ctx)
        Lexer, Parser = self.make('''grammar G;
            start: child EOF;
            catch [RuntimeError as error] {self.message = str(error)}
            finally {self.done = True}
            child: INT;
            finally {raise RuntimeError('from finally')}
            INT: [0-9]+;
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        parser.start()
        self.assertEqual('from finally', parser.message)
        self.assertTrue(parser.done)
        self.assertIsNone(parser._ctx)

    def test_invalid_exception_and_nonlocal_syntax_leaves_no_outputs(self):
        for text in [
            "grammar G; start: 'x' {$absent::value = 1};",
            "grammar G; start returns [value:int]: 'x' {$start::missing = 1};",
            "grammar G; start: 'x'; catch [Exception e] {pass}",
            "grammar G; start: 'x'; catch [Exception as self] {pass}",
            "grammar G; start: 'x'; catch [] {pass} catch [Exception] {pass}",
            "grammar G; start: start '+' INT | INT; catch [Exception] {pass} INT:[0-9]+;",
            "grammar G; start: start '+' INT | INT; finally {pass} INT:[0-9]+;",
            "lexer grammar G; X:'x'; finally {pass}",
        ]:
            with self.subTest(grammar=text):
                path = self.root / 'G.g4'
                path.write_text(text)
                output = self.root / 'bad'
                with self.assertRaises(GrammarError):
                    generate(path, output)
                self.assertFalse(output.exists())

    def test_exception_replacement_bare_raise_and_catch_all(self):
        Lexer, Parser = self.make('''grammar G;
            start: child EOF;
            catch [KeyError as problem] {self.message = str(problem)}
            finally {self.events.append('outer')}
            child: INT {raise ValueError('first')};
            catch [ValueError] {raise KeyError('replacement')}
            finally {self.events.append('inner'); raise}
            INT:[0-9]+;
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        parser.events = []
        parser.start()
        self.assertEqual("'replacement'", parser.message)
        self.assertEqual(['inner', 'outer'], parser.events)
        self.assertIsNone(parser._ctx)
        Lexer, Parser = self.make('''grammar G;
            start: INT {raise SystemExit('caught')};
            catch [] {self.message = 'all'}
            finally {self.done = True}
            INT:[0-9]+;
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        parser.start()
        self.assertEqual('all', parser.message)
        self.assertTrue(parser.done)

    def test_strict_recognition_exception_can_be_caught_by_grammar(self):
        Lexer, Parser = self.make('''grammar G;
            start returns [value:int]: INT ';' EOF;
            catch [RecognitionException as problem] {
self.problem = type(problem).__name__
$value = -1
}
            finally {self.done = True}
            INT:[0-9]+;
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        self.assertEqual(-1, parser.start().value)
        self.assertEqual('InputMismatchException', parser.problem)
        self.assertEqual(0, parser.getNumberOfSyntaxErrors())
        self.assertTrue(parser.done)

    def test_imported_exception_clauses_and_nonlocal_indices(self):
        (self.root / 'Base.g4').write_text('''grammar Base;
            parent returns [value:int=0]: child;
            finally {self.events.append('parent')}
            child: INT {$parent::value = $INT.int} {raise ValueError('handled')};
            catch [ValueError] {self.events.append('catch')}
            finally {self.events.append('child')}
            INT:[0-9]+;
        ''')
        Lexer, Parser = self.make('''grammar G; import Base;
            start returns [value:int]: parent EOF {$value = $parent.value};
        ''')
        parser = Parser(CommonTokenStream(Lexer(InputStream('7'))))
        parser.events = []
        self.assertEqual(7, parser.start().value)
        self.assertEqual(['catch', 'child', 'parent'], parser.events)

    def test_inactive_nonlocal_scope_restores_parser_state(self):
        Lexer, Parser = self.fixture('Nonlocals')
        parser = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        parser.events, parser.limit = [], 100
        with self.assertRaises(AttributeError):
            parser.item()
        self.assertIsNone(parser._ctx)
        self.assertEqual([0], parser._precedenceStack)

    def test_reference_exceptions_and_nonlocal_scopes(self):
        reference = json.loads((FIXTURES / 'exceptions_reference.json').read_text())
        for name, cases in reference['grammars'].items():
            Lexer, Parser = self.fixture(name)
            for case in cases:
                with self.subTest(grammar=name, case=case):
                    self.assertEqual(case['snapshot'], snapshot(Lexer, Parser, case, generated=True))


if __name__ == '__main__':
    unittest.main()
