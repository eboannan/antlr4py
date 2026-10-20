import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4.Token import Token
from antlr4_generator import GrammarError, generate
from antlr4_generator.grammar import read_grammar


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, path.stem)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make(self, text):
        grammar = self.root / 'test.g4'
        grammar.write_text(text)
        paths = generate(grammar, self.root / 'generated')
        return load(paths[0]), load(paths[1])

    def test_generate_parse_and_errors(self):
        Lexer, Parser = self.make(r"""grammar Numbers;
            start: INT (',' INT)* EOF;
            INT: [0-9]+;
            WS: [ \t\r\n]+ -> skip;
        """)
        lexer = Lexer(InputStream('12,\n 34,56'))
        stream = CommonTokenStream(lexer)
        parser = Parser(stream)
        tree = parser.start()
        self.assertEqual('(start 12 , 34 , 56 <EOF>)', tree.toStringTree(recog=parser))
        self.assertEqual('12,34,56<EOF>', tree.getText())
        stream.fill()
        token = stream.tokens[2]
        self.assertEqual(('34', 2, 1, 5, 6),
                         (token.text, token.line, token.column, token.start, token.stop))
        self.assertEqual(Token.EOF, stream.tokens[-1].type)
        with self.assertRaisesRegex(SyntaxError, 'Expected'):
            Parser(CommonTokenStream(Lexer(InputStream('12,')))).start()
        with self.assertRaisesRegex(SyntaxError, 'Unexpected character'):
            Parser(CommonTokenStream(Lexer(InputStream('12@')))).start()
        lexer.reset()
        self.assertEqual(('12', 1, 0),
                         (lexer.nextToken().text, lexer.line, lexer.column - 2))

    def test_longest_match_literal_priority_and_explicit_token(self):
        Lexer, Parser = self.make("""grammar Words;
            start: 'if' ID PLUS ID EOF;
            PLUS: '+';
            ID: [a-z]+;
            WS: ' '+ -> skip;
        """)
        parser = Parser(CommonTokenStream(Lexer(InputStream('if iffy+x'))))
        self.assertEqual('(start if iffy + x <EOF>)', parser.start().toStringTree(recog=parser))
        lexer = Lexer(InputStream('iffy'))
        self.assertEqual(Parser.ID, lexer.nextToken().type)

    def test_rules_alternatives_optional_and_right_recursion(self):
        Lexer, Parser = self.make("""grammar Tree;
            start: item+ EOF;
            item: '(' item* ')' | ID '!'?;
            ID: [a-z]+;
            WS: ' '+ -> skip;
        """)
        parser = Parser(CommonTokenStream(Lexer(InputStream('(a (b)) c!'))))
        self.assertEqual('(start (item ( (item a) (item ( (item b) )) )) (item c !) <EOF>)',
                         parser.start().toStringTree(recog=parser))

    def test_empty_alternative(self):
        Lexer, Parser = self.make("grammar Empty; start: maybe 'b' EOF; maybe: 'a' | ;")
        parser = Parser(CommonTokenStream(Lexer(InputStream('b'))))
        self.assertEqual('(start maybe b <EOF>)', parser.start().toStringTree(recog=parser))

    def test_unsupported_and_invalid_grammars(self):
        cases = [
            "grammar G; start: missing EOF;",
            "grammar G; start: start 'x';",
            "grammar G; start: next; next: start | 'x';",
            "grammar G; start: ('x'?)* EOF;",
            "grammar G; start: X; X: [z-a];",
            "grammar G; start: X; X: 'x'*;",
            "grammar G; start: 'x'; start: 'y';",
            "grammar G; atn: 'x';",
            "grammar G; getRuleInvocationStack: 'x';",
            "grammar G; start: SKIP; SKIP: 'x';",
            "grammar G; start: [a-z];",
            "grammar G; start: 'x' -> skip;",
            "grammar G; start: '\\p';",
            "grammar G; start: '';",
            "grammar G; start: 'x' EOF*;",
            "grammar G; start: 'x'; T__0: 'y';",
            "grammar G; start: 'x' EOF",  # missing semicolon
        ]
        for text in cases:
            with self.subTest(grammar=text), self.assertRaises(GrammarError):
                read_grammar(text)

    def test_protect_output_and_determinism(self):
        grammar = self.root / 'G.g4'
        grammar.write_text("grammar G; start: 'x' EOF;")
        paths = generate(grammar, self.root)
        before = [p.read_bytes() for p in paths]
        with self.assertRaises(FileExistsError):
            generate(grammar, self.root)
        generate(grammar, self.root, overwrite=True)
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_cli_with_no_programs_on_path(self):
        grammar = self.root / 'G.g4'
        grammar.write_text("grammar G; start: 'x' EOF;")
        environment = dict(os.environ, PATH=str(self.root / 'no-tools'))
        result = subprocess.run([sys.executable, '-m', 'antlr4_generator', str(grammar),
                                 '-o', str(self.root / 'generated')],
                                env=environment, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        Lexer = load(self.root / 'generated/GLexer.py')
        Parser = load(self.root / 'generated/GParser.py')
        self.assertEqual('x<EOF>', Parser(CommonTokenStream(Lexer(InputStream('x')))).start().getText())
        grammar.write_text("grammar G; start: unknown;")
        result = subprocess.run([sys.executable, '-m', 'antlr4_generator', str(grammar)],
                                env=environment, capture_output=True, text=True)
        self.assertEqual(1, result.returncode)
        self.assertIn('Undefined reference', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_invalid_grammar_creates_no_outputs(self):
        grammar = self.root / 'G.g4'
        grammar.write_text("grammar G; start: start 'x';")
        output = self.root / 'generated'
        with self.assertRaises(GrammarError):
            generate(grammar, output)
        self.assertFalse(output.exists())

    def test_comments_keyword_priority_and_rule_order(self):
        Lexer, Parser = self.make(r"""// keyword must beat ID at the same length
            grammar Keywords;
            /* literal uses the named token, without adding an implicit token */
            start: 'if' ID EOF;
            IF: 'if';
            ID: [a-z]+;
            WS: ' '+ -> skip;
        """)
        stream = CommonTokenStream(Lexer(InputStream('if iffy')))
        parser = Parser(stream)
        parser.start()
        self.assertEqual([Parser.IF, Parser.ID, Token.EOF], [t.type for t in stream.tokens])
        self.assertEqual(1, Parser.IF)


if __name__ == '__main__':
    unittest.main()
