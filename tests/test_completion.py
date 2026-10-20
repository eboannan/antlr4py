import json
from pathlib import Path
import sys
import os
import subprocess
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4_generator import generate
from test_atn import load
from completion_probe import snapshot


FIXTURES = Path(__file__).with_name('fixtures')


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_reference_completed_features(self):
        reference = json.loads((FIXTURES / 'completion_reference.json').read_text())
        for name, cases in reference['grammars'].items():
            paths = generate(FIXTURES / (name+'.g4'), self.root, visitor=True)
            is_lexer = len(paths) == 1
            Lexer = getattr(load(paths[0]), name if is_lexer else name+'Lexer')
            Parser = None if is_lexer else getattr(load(paths[1]), name+'Parser')
            for case in cases:
                with self.subTest(grammar=name, input=case['input'], entry=case.get('entry')):
                    self.assertEqual(case['snapshot'], snapshot(Lexer, Parser, case, generated=True))

    def test_custom_parser_lexer_and_context_bases(self):
        path = self.root / 'G.g4'
        path.write_text('''grammar G;
            options {language=Python3; superClass=BaseParser; contextSuperClass=BaseContext;}
            @parser::header {
from antlr4 import Parser, ParserRuleContext
class BaseParser(Parser):
    def marker(self): return 'parser'
class BaseContext(ParserRuleContext):
    def marker(self): return 'context'
}
            start: INT EOF; INT:[0-9]+;
        ''')
        lexer, parser = generate(path, self.root)
        Lexer, Parser = load(lexer).GLexer, load(parser).GParser
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        self.assertEqual('parser', recognizer.marker())
        self.assertEqual('context', recognizer.start().marker())
        path.write_text('''lexer grammar G;
            options {superClass=BaseLexer;}
            @header {
from antlr4 import Lexer
class BaseLexer(Lexer):
    def marker(self): return 'lexer'
}
            WORD:[a-z]+;
        ''')
        (module,) = generate(path, self.root, overwrite=True)
        lexer = load(module).G(InputStream('abc'))
        self.assertEqual('lexer', lexer.marker())
        self.assertEqual('abc', lexer.nextToken().text)

    def test_alias_import_and_implicit_parser_token(self):
        (self.root / 'Base.g4').write_text('parser grammar Base; atom: ID;')
        path = self.root / 'G.g4'
        path.write_text("grammar G; import Alias=Base; start:atom EOF; ID:[a-z]+;")
        lexer, parser = generate(path, self.root)
        Lexer, Parser = load(lexer).GLexer, load(parser).GParser
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('hello'))))
        self.assertEqual('(start (atom hello) <EOF>)', recognizer.start().toStringTree(recog=recognizer))

    def test_action_closures_early_return_and_finally_override(self):
        lexer, parser = generate(FIXTURES / 'Scopes.g4', self.root)
        Lexer, Parser = load(lexer).ScopesLexer, load(parser).ScopesParser
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('4'))))
        self.assertEqual(5, recognizer.closure().value)
        self.assertEqual(5, recognizer.read())
        recognizer.reset()
        self.assertEqual(42, recognizer.handled())
        self.assertTrue(recognizer.cleaned)
        self.assertIsNone(recognizer._ctx)

        path = self.root / 'Return.g4'
        path.write_text('''grammar Return;
            start: child EOF;
            child: INT {raise ValueError('suppressed')};
            finally {return 99}
            INT:[0-9]+;
        ''')
        lexer, parser = generate(path, self.root)
        Lexer, Parser = load(lexer).ReturnLexer, load(parser).ReturnParser
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        self.assertEqual(99, recognizer.child())
        self.assertIsNone(recognizer._ctx)

    def test_cli_multiple_inputs_options_encoding_and_package(self):
        lexer = self.root / 'Words.g4'
        lexer.write_bytes("lexer grammar Words; WORD:'café'; WS:' '+ -> channel(1);".encode('latin-1'))
        parser = self.root / 'Sentence.g4'
        parser.write_text('parser grammar Sentence; options{tokenVocab=Words;} start:WORD EOF;')
        output = self.root / 'generated'
        result = subprocess.run([sys.executable, '-m', 'antlr4_generator', str(parser), str(lexer),
                                 '-Dlanguage=Python3', '-DcaseInsensitive=true', '-encoding', 'latin-1',
                                 '-package', 'generated', '-Xexact-output-dir', '-o', str(output)],
                                env=dict(os.environ, PATH=str(self.root / 'no-tools')), capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((output / '__init__.py').exists())
        Lexer, Parser = load(output / 'Words.py').Words, load(output / 'Sentence.py').Sentence
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('CAFÉ'))))
        self.assertEqual('CAFÉ<EOF>', recognizer.start().getText())

    def test_numeric_lexer_commands_and_python_target_rule_options(self):
        path = self.root / 'G.g4'
        path.write_text('''grammar G; options{language='Python3';}
            public start returns [value:int] throws Exception locals [saved:int=2]
                : (options{}: NUMBER) EOF {$value=$saved};
            tokensPlaceholder: ;
            NUMBER:[0-9]+;
            WS:' '+ -> channel(1);
        ''')
        lexer, parser = generate(path, self.root)
        Lexer, Parser = load(lexer).GLexer, load(parser).GParser
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('12 '))))
        self.assertEqual(2, recognizer.start().value)

    def test_grammar_option_override_and_predicate_failure_message(self):
        path = self.root / 'G.g4'
        path.write_text('''grammar G; options{language=Java;}
            start: INT {False}?<fail='custom failure'> EOF;
            INT:[0-9]+;
        ''')
        lexer, parser = generate(path, self.root, options={'language':'Python3'})
        Lexer, Parser = load(lexer).GLexer, load(parser).GParser
        from antlr4.error.ErrorListener import ErrorListener
        messages = []
        class Errors(ErrorListener):
            def syntaxError(self, recognizer, token, line, column, message, error):
                messages.append(message)
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('1'))), recover=True)
        recognizer.removeErrorListeners()
        recognizer.addErrorListener(Errors())
        recognizer.start()
        self.assertEqual(['rule start custom failure'], messages)

    def test_python_reserved_identifiers_match_target_api(self):
        lexer, parser = generate(FIXTURES / 'Reserved.g4', self.root)
        Lexer, Parser = load(lexer).ReservedLexer, load(parser).ReservedParser
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('word'))))
        tree = recognizer.start()
        self.assertEqual(7, tree.value)
        self.assertTrue(callable(recognizer.class_))
        self.assertEqual(3, tree.result.int_)
        self.assertEqual('word', tree.result.for_.text)
        self.assertEqual(Lexer.TRUTH, Parser.TRUTH)
        self.assertTrue(callable(recognizer.reset_))

    def test_python_initializers_and_mutable_argument_defaults(self):
        path = self.root / 'G.g4'
        path.write_text('''grammar G;
            start: child EOF;
            child[items:list=[]] locals [data:dict=dict()]: INT
                {$items.append($INT.int)} {$data['value']=$INT.int};
            INT:[0-9]+;
        ''')
        lexer, parser = generate(path, self.root)
        Lexer, Parser = load(lexer).GLexer, load(parser).GParser
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('1'))))
        first = recognizer.child()
        recognizer.reset()
        second = recognizer.child()
        self.assertEqual([1], first.items)
        self.assertEqual([1], second.items)
        self.assertIsNot(first.items, second.items)
        self.assertIsNot(first.data, second.data)
        recognizer.reset()
        explicit = []
        self.assertIs(explicit, recognizer.child(explicit).items)



if __name__ == '__main__':
    unittest.main()
