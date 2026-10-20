import json
from pathlib import Path
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4.Token import Token
from antlr4.atn.ATNDeserializer import ATNDeserializer
from antlr4_generator import GrammarError, generate
from antlr4_generator.atn import serialize_atn
from antlr4_generator.grammar import read_grammar
from test_atn import load


class LexerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make(self, text):
        path = self.root / 'G.g4'
        path.write_text(text)
        paths = generate(path, self.root, overwrite=True)
        module = load(paths[0])
        return getattr(module, paths[0].stem)

    def tokens(self, Lexer, text):
        stream = CommonTokenStream(Lexer(InputStream(text)))
        stream.fill()
        return stream.tokens

    def test_fragments_and_longest_alternative(self):
        Lexer = self.make("""lexer grammar G;
            fragment DIGIT: [0-9];
            NUMBER: DIGIT+ ('.' DIGIT+)?;
            WORD: 'a' | 'ab';
            WS: ' '+ -> skip;
        """)
        self.assertEqual(['12.34', 'ab', 'a', '<EOF>'],
                         [t.text for t in self.tokens(Lexer, '12.34 ab a')])
        self.assertEqual(['DIGIT', 'NUMBER', 'WORD', 'WS'], Lexer.ruleNames)
        self.assertFalse(hasattr(Lexer, 'DIGIT'))
        self.assertEqual(1, Lexer.NUMBER)
        Lexer = self.make("lexer grammar G; fragment OPTIONAL: 'a'?; TOKEN: OPTIONAL 'b';")
        self.assertEqual(['b', 'ab', '<EOF>'], [t.text for t in self.tokens(Lexer, 'bab')])

    def test_unicode_sets_ranges_properties_and_escapes(self):
        Lexer = self.make(r"""lexer grammar G;
            EMOJI: '\u{1F600}'..'\u{1F64F}';
            LETTER: [\p{General_Category=Letter}]+;
            NUMBER: [\p{Nd}]+;
            SPACE: [\u0009-\u000D ]+ -> skip;
        """)
        tokens = self.tokens(Lexer, 'αβ 中文 ١٢ 😀')
        self.assertEqual(['αβ', '中文', '١٢', '😀', '<EOF>'], [t.text for t in tokens])
        self.assertEqual([Lexer.LETTER, Lexer.LETTER, Lexer.NUMBER, Lexer.EMOJI, Token.EOF],
                         [t.type for t in tokens])
        Lexer = self.make(r"lexer grammar G; PAIR: '\uD83D\uDE00'; OTHER: [\P{L}]+;")
        self.assertEqual(Lexer.PAIR, self.tokens(Lexer, '😀')[0].type)

    def test_negation_nongreedy_and_hidden_channel(self):
        Lexer = self.make(r"""lexer grammar G;
            COMMENT: '/*' .*? '*/' -> channel(HIDDEN);
            TEXT: ~('/' | '*')+;
        """)
        tokens = self.tokens(Lexer, '/*a*/text/*b*/')
        self.assertEqual(['/*a*/', 'text', '/*b*/', '<EOF>'], [t.text for t in tokens])
        self.assertEqual([1, 0, 1, 0], [t.channel for t in tokens])

    def test_mode_more_retype_and_reset(self):
        fixture = Path(__file__).with_name('fixtures') / 'Modes.g4'
        (path,) = generate(fixture, self.root)
        Lexer = getattr(load(path), 'Modes')
        lexer = Lexer(InputStream('"a\\\"b"'))
        token = lexer.nextToken()
        self.assertEqual(('"a\\\"b"', Lexer.STRING), (token.text, token.type))
        self.assertEqual(0, lexer._mode)
        self.assertEqual([], lexer._modeStack)
        lexer.reset()
        self.assertEqual(token.text, lexer.nextToken().text)
        self.assertEqual(['DEFAULT_MODE', 'QUOTED', 'TAGMODE'], Lexer.modeNames)
        self.assertEqual(2, Lexer.COMMENTS)

    def test_combined_lexer_alternatives_and_fragments(self):
        path = self.root / 'G.g4'
        path.write_text("grammar G; start: NUMBER EOF; NUMBER: DIGIT+ ('.' DIGIT+)?; fragment DIGIT: [0-9];")
        lexer_path, parser_path = generate(path, self.root)
        Lexer, Parser = getattr(load(lexer_path), 'GLexer'), getattr(load(parser_path), 'GParser')
        parser = Parser(CommonTokenStream(Lexer(InputStream('12.34'))))
        self.assertEqual('(start 12.34 <EOF>)', parser.start().toStringTree(recog=parser))

    def test_invalid_constructs_are_rejected(self):
        for source in [
            "lexer grammar G; A: B;", "lexer grammar G; A: B; fragment B: A;",
            "lexer grammar G; A: ('a'?)*;", "lexer grammar G; fragment F: 'a';",
            "lexer grammar G; A: 'a' -> unknown;", "lexer grammar G; A: 'a' -> type(MISSING);",
            "lexer grammar G; A: 'a' -> pushMode(MISSING);",
            "lexer grammar G; A: 'a' -> skip, more;", "lexer grammar G; A: 'a' -> skip(1);",
            "lexer grammar G; A: 'a' -> channel(MISSING);",
            "lexer grammar G; A: 'a' -> skip, skip;",
            "lexer grammar G; A: 'a' -> channel(HIDDEN), skip;",
            "lexer grammar G; channels { HIDDEN } A: 'a';",
            "grammar G; tokens { T__0 } start: 'a';",
            "lexer grammar G; fragment F: 'a' -> skip; A: F;",
            "lexer grammar G; A: ('a' -> skip);",
            "lexer grammar G; A: 'a' -> skip | 'b';",
            "lexer grammar G; A: ~'ab';", "lexer grammar G; A: [z-a];",
            r"lexer grammar G; A: [\p{Script=Imaginary}];",
            r"lexer grammar G; A: [\u{110000}];",
            "grammar G; start: 'a'; mode EXTRA; A: 'b';",
            "lexer grammar G; A: 'a'; mode EXTRA; fragment F: 'x';",
            "lexer grammar G; A: 'a'; mode EXTRA; B: 'b'; mode EXTRA; C: 'c';",
        ]:
            with self.subTest(source=source), self.assertRaises(GrammarError):
                read_grammar(source)

    def test_reference_lexers(self):
        fixtures = Path(__file__).with_name('fixtures')
        reference = json.loads((fixtures / 'reference.json').read_text())
        for name, snapshot in reference['lexers'].items():
            (path,) = generate(fixtures / (name+'.g4'), self.root)
            Lexer = getattr(load(path), name)
            self.assertEqual(snapshot['lexer_atn'], serialize_atn(
                ATNDeserializer().deserialize(snapshot['lexer_atn'])))
            for case in snapshot['cases']:
                with self.subTest(grammar=name, input=case['input']):
                    lexer = Lexer(InputStream(case['input']))
                    stream = CommonTokenStream(lexer)
                    if 'error' in case:
                        with self.assertRaises(SyntaxError):
                            stream.fill()
                    else:
                        stream.fill()
                        self.assertEqual(case['tokens'], [
                            [t.type, t.text, t.line, t.column, t.start, t.stop, t.channel]
                            for t in stream.tokens])
                        self.assertEqual(case['mode'], lexer._mode)
                        self.assertEqual(case['mode_stack'], lexer._modeStack)


if __name__ == '__main__':
    unittest.main()
