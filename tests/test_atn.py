import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4.Token import Token
from antlr4.atn.ATNDeserializer import ATNDeserializer
from antlr4.atn.ATNType import ATNType
from antlr4.atn.ATNState import RuleStopState
from antlr4.atn.LexerATNSimulator import LexerATNSimulator
from antlr4.atn.ParserATNSimulator import ParserATNSimulator
from antlr4.atn.Transition import RuleTransition
from antlr4_generator import generate
from antlr4_generator.atn import build_atns, serialize_atn
from antlr4_generator.grammar import read_grammar


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ATNTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make(self, text):
        path = self.root / 'G.g4'
        path.write_text(text)
        lexer_path, parser_path = generate(path, self.root, overwrite=True)
        return getattr(load(lexer_path), lexer_path.stem), getattr(load(parser_path), parser_path.stem)

    def test_native_simulators_and_rule_return_edges(self):
        grammar = read_grammar(r"""grammar G;
            start: item+ EOF;
            item: '(' item* ')' | INT '!'? | INT '?';
            INT: [0-9]+;
            WS: [ \t\r\n]+ -> skip;
        """)
        lexer_atn, parser_atn = build_atns(grammar)
        self.assertEqual(ATNType.LEXER, lexer_atn.grammarType)
        self.assertEqual(ATNType.PARSER, parser_atn.grammarType)
        for atn in (lexer_atn, parser_atn):
            data = serialize_atn(atn)
            self.assertEqual(data, serialize_atn(ATNDeserializer().deserialize(data)))
        for state in parser_atn.states:
            for edge in state.transitions:
                if isinstance(edge, RuleTransition):
                    stop = parser_atn.ruleToStopState[edge.ruleIndex]
                    self.assertIsInstance(stop, RuleStopState)
                    self.assertTrue(any(t.target is edge.followState for t in stop.transitions))
        Lexer, Parser = self.make(r"""grammar G;
            start: item+ EOF;
            item: '(' item* ')' | INT '!'? | INT '?';
            INT: [0-9]+;
            WS: [ \t\r\n]+ -> skip;
        """)
        lexer = Lexer(InputStream('(1 2!)'))
        parser = Parser(CommonTokenStream(lexer))
        self.assertIsInstance(lexer._interp, LexerATNSimulator)
        self.assertIsInstance(parser._interp, ParserATNSimulator)
        self.assertEqual('(start (item ( (item 1) (item 2 !) )) <EOF>)',
                         parser.start().toStringTree(recog=parser))
        self.assertTrue(any(dfa.states for dfa in parser._interp.decisionToDFA))

    def test_shared_prefix_prediction(self):
        Lexer, Parser = self.make("grammar G; start: ('a' 'b' | 'a' 'c') EOF;")
        for text in ('ab', 'ac'):
            with self.subTest(text=text):
                parser = Parser(CommonTokenStream(Lexer(InputStream(text))))
                self.assertEqual(text+'<EOF>', parser.start().getText())
        with self.assertRaises(SyntaxError):
            Parser(CommonTokenStream(Lexer(InputStream('aa')))).start()

    def test_prediction_through_rule_returns_and_cached_contexts(self):
        Lexer, Parser = self.make("""grammar G;
            start: 'p' optional 'x' EOF | 'q' optional 'y' EOF;
            optional: 'x' | ;
        """)
        parser = Parser(CommonTokenStream(Lexer(InputStream('px'))))
        for text, expected in [
            ('px', '(start p optional x <EOF>)'),
            ('pxx', '(start p (optional x) x <EOF>)'),
            ('qy', '(start q optional y <EOF>)'),
            ('qxy', '(start q (optional x) y <EOF>)'),
        ]:
            with self.subTest(text=text):
                parser.setInputStream(CommonTokenStream(Lexer(InputStream(text))))
                self.assertEqual(expected, parser.start().toStringTree(recog=parser))
                self.assertIsNone(parser._ctx)

    def test_loop_exit_uses_continuation(self):
        for operator in ('*', '+', '?'):
            Lexer, Parser = self.make(f"grammar G; start: 'x'{operator} 'x' EOF;")
            for text in (['x', 'xx'] if operator != '+' else ['xx', 'xxx']):
                with self.subTest(operator=operator, text=text):
                    parser = Parser(CommonTokenStream(Lexer(InputStream(text))))
                    self.assertEqual(text+'<EOF>', parser.start().getText())

    def test_failure_restores_context_and_reset(self):
        Lexer, Parser = self.make("grammar G; start: item EOF; item: '(' 'a' ')';")
        parser = Parser(CommonTokenStream(Lexer(InputStream('(a'))))
        with self.assertRaises(SyntaxError):
            parser.start()
        self.assertEqual(1, parser.getNumberOfSyntaxErrors())
        self.assertIsNone(parser._ctx)
        parser.setInputStream(CommonTokenStream(Lexer(InputStream('(a)'))))
        self.assertEqual('(a)<EOF>', parser.start().getText())
        self.assertEqual(0, parser.getNumberOfSyntaxErrors())
        for text in ('@', '(a@'):
            parser.setInputStream(CommonTokenStream(Lexer(InputStream(text))))
            with self.subTest(input=text), self.assertRaises(SyntaxError):
                parser.start()
            self.assertIsNone(parser._ctx)

    def test_reference_fixtures(self):
        fixtures = Path(__file__).with_name('fixtures')
        snapshots = json.loads((fixtures / 'reference.json').read_text())
        self.assertEqual('4.13.2', snapshots['antlr_version'])
        for name, reference in snapshots['grammars'].items():
            with self.subTest(grammar=name):
                grammar = fixtures / (name+'.g4')
                lexer_path, parser_path = generate(grammar, self.root, overwrite=True)
                lexer_module, parser_module = load(lexer_path), load(parser_path)
                Lexer, Parser = getattr(lexer_module, name+'Lexer'), getattr(parser_module, name+'Parser')
                # The serializer must also preserve ATNs emitted by the Java tool,
                # not merely round-trip its own builder's output.
                for key in ('lexer_atn', 'parser_atn'):
                    data = reference[key]
                    self.assertEqual(data, serialize_atn(ATNDeserializer().deserialize(data)))
                for case in reference['cases']:
                    with self.subTest(input=case['input']):
                        lexer = Lexer(InputStream(case['input']))
                        stream = CommonTokenStream(lexer)
                        parser = Parser(stream)
                        if 'error' in case:
                            with self.assertRaises(SyntaxError):
                                parser.start()
                        else:
                            tree = parser.start()
                            stream.fill()
                            self.assertEqual(case['tree'], tree.toStringTree(recog=parser))
                            self.assertEqual(case['tokens'], [
                                [t.type, t.text, t.line, t.column, t.start, t.stop, t.channel]
                                for t in stream.tokens])


if __name__ == '__main__':
    unittest.main()
