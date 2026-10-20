import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4.ListTokenSource import ListTokenSource
from antlr4.Token import CommonToken, Token
from antlr4_generator import GrammarError, generate
from antlr4_generator.composition import read_vocabulary
from test_atn import load


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'generated'

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_separate_lexer_parser_and_literal_aliases(self):
        lexer = self.write('Words.g4', "lexer grammar Words; ID: [a-z]+; PLUS: '+'; WS: ' '+ -> skip;")
        parser = self.write('Sentence.g4', "parser grammar Sentence; options { tokenVocab=Words; } start: ID ('+' ID)* EOF;")
        (lexer_path,) = generate(lexer, self.output)
        (parser_path,) = generate(parser, self.output)
        Lexer, Parser = load(lexer_path).Words, load(parser_path).Sentence
        recognizer = Parser(CommonTokenStream(Lexer(InputStream('a + b'))))
        self.assertEqual('(start a + b <EOF>)', recognizer.start().toStringTree(recog=recognizer))
        self.assertEqual(Lexer.PLUS, Parser.PLUS)
        vocab = read_vocabulary(self.output / 'Words.tokens')
        self.assertEqual(Parser.PLUS, vocab.literals['+'])
        self.assertFalse((self.output / 'SentenceLexer.py').exists())

    def test_sparse_ids_aliases_and_new_token_allocation(self):
        self.write('Sparse.tokens', "ID=7\nALIAS=7\nPLUS=23\n'+'=23\n")
        parser = self.write('P.g4', "parser grammar P; options {tokenVocab=Sparse;} tokens { EXTRA } start: ID '+' ALIAS EOF;")
        (module_path,) = generate(parser, self.output)
        Parser = load(module_path).P
        self.assertEqual((7, 7, 23, 24), (Parser.ID, Parser.ALIAS, Parser.PLUS, Parser.EXTRA))
        self.assertEqual(24, Parser.atn.maxTokenType)
        self.assertEqual('PLUS', Parser.symbolicNames[23])
        self.assertEqual("'+'", Parser.literalNames[23])
        self.assertEqual(24, read_vocabulary(self.output / 'P.tokens').names['EXTRA'])
        tokens = []
        for kind, text in [(7, 'a'), (23, '+'), (7, 'b'), (Token.EOF, '<EOF>')]:
            token = CommonToken(type=kind)
            token.text = text
            tokens.append(token)
        recognizer = Parser(CommonTokenStream(ListTokenSource(tokens)))
        self.assertEqual('(start a + b <EOF>)', recognizer.start().toStringTree(recog=recognizer))

    def test_combined_vocab_preserves_existing_implicit_names(self):
        self.write('V.tokens', "T__0=8\n'old'=8\n")
        source = self.write('G.g4', "grammar G; options {tokenVocab=V;} start: 'new' EOF;")
        generate(source, self.output)
        vocab = read_vocabulary(self.output / 'G.tokens')
        self.assertEqual(8, vocab.names['T__0'])
        self.assertEqual(9, vocab.literals['new'])

    def test_combined_and_lexer_import_overrides(self):
        self.write('Base.g4', "grammar Base; item: ID; ID: [a-z]+; WS: ' '+ -> skip;")
        root = self.write('Root.g4', "grammar Root; import Base; start: item EOF; item: ID ID;")
        lexer_path, parser_path = generate(root, self.output)
        Lexer, Parser = load(lexer_path).RootLexer, load(parser_path).RootParser
        parser = Parser(CommonTokenStream(Lexer(InputStream('a b'))))
        self.assertEqual('(start (item a b) <EOF>)', parser.start().toStringTree(recog=parser))
        self.assertEqual(['start', 'item'], Parser.ruleNames)
        self.write('Letters.g4', "lexer grammar Letters; WORD: LETTER+; fragment LETTER: [a-z]; WS: ' '+ -> skip;")
        lexer = self.write('Digits.g4', "lexer grammar Digits; import Letters; fragment LETTER: [0-9];")
        (path,) = generate(lexer, self.output)
        tokens = load(path).Digits(InputStream('123')).getAllTokens()
        self.assertEqual(['123'], [t.text for t in tokens])
        with self.assertRaises(SyntaxError):
            load(path).Digits(InputStream('abc')).getAllTokens()

    def test_transitive_import_preorder_and_first_import_wins(self):
        self.write('D.g4', "parser grammar D; atom: 'd';")
        self.write('A.g4', "parser grammar A; import D; a: atom;")
        self.write('B.g4', "parser grammar B; atom: 'b';")
        source = self.write('Root.g4', "grammar Root; import A,B; start: a EOF;")
        lexer_path, parser_path = generate(source, self.output)
        Lexer, Parser = load(lexer_path).RootLexer, load(parser_path).RootParser
        parser = Parser(CommonTokenStream(Lexer(InputStream('d'))))
        self.assertEqual('(start (a (atom d)) <EOF>)', parser.start().toStringTree(recog=parser))

    def test_library_resolution_and_java_free_cli(self):
        self.write('lib/Base.g4', "parser grammar Base; item: ID;")
        self.write('lib/V.tokens', 'ID=4\n')
        grammar = self.write('app/P.g4', 'parser grammar P; options {tokenVocab=V;} import Base; start: item EOF;')
        result = subprocess.run([sys.executable, '-m', 'antlr4_generator', str(grammar),
                                 '-lib', str(self.root / 'lib'), '-o', str(self.output)],
                                env=dict(os.environ, PATH=str(self.root / 'no-tools')),
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(4, load(self.output / 'P.py').P.ID)

    def test_invalid_dependencies_write_no_outputs(self):
        cases = [
            ('parser grammar P; options {tokenVocab=Missing;} start: ID EOF;', {}),
            ('parser grammar P; import Missing; start: item EOF;', {}),
            ('parser grammar P; options {tokenVocab=V;} start: ID EOF;', {'V.tokens': 'ID=bad\n'}),
            ('parser grammar P; options {tokenVocab=V;} start: ID EOF;', {'V.tokens': 'ID=1\nID=2\n'}),
            ("parser grammar P; options {tokenVocab=V;} start: 'missing' EOF;", {'V.tokens': 'ID=1\n'}),
            ('parser grammar P; import A; start: item EOF;', {'A.g4': 'parser grammar A; import P; item: ID;'}),
            ('parser grammar P; import A; start: item EOF;', {'A.g4': 'lexer grammar A; ID: [a-z]+;'}),
            ('parser grammar P; import A; start: item EOF;', {'A.g4': 'parser grammar Wrong; item: ID;'}),
            ('parser grammar P; options {language=Python4;} start: ID;', {}),
            ('parser grammar P; ID: [a-z]+;', {}),
            ('parser grammar P; import Alias=; start: ID;', {'A.g4': 'parser grammar A; a: ID;'}),
        ]
        for index, (text, dependencies) in enumerate(cases):
            directory = self.root / str(index)
            source = self.write(f'{index}/P.g4', text)
            for name, content in dependencies.items():
                self.write(f'{index}/{name}', content)
            with self.subTest(grammar=text), self.assertRaises(GrammarError):
                generate(source, directory / 'out')
            self.assertFalse((directory / 'out').exists())

    def test_sidecar_collision_protects_all_outputs(self):
        source = self.write('G.g4', "grammar G; start: 'a' EOF;")
        self.output.mkdir()
        sidecar = self.output / 'G.tokens'
        sidecar.write_text('user content')
        with self.assertRaises(FileExistsError):
            generate(source, self.output)
        self.assertEqual('user content', sidecar.read_text())
        self.assertFalse((self.output / 'GLexer.py').exists())
        generate(source, self.output, overwrite=True)
        self.assertEqual(read_vocabulary(sidecar), read_vocabulary(self.output / 'GLexer.tokens'))

    def test_reference_composition_and_external_vocabularies(self):
        fixtures = Path(__file__).with_name('fixtures') / 'composition'
        reference = json.loads((fixtures / 'reference.json').read_text())
        self.assertEqual('4.13.2', reference['antlr_version'])
        for index, scenario in enumerate(reference['scenarios']):
            output = self.output / str(index)
            for name in scenario['generate']:
                generate(fixtures / (name+'.g4'), output)
            Lexer = getattr(load(output / (scenario['lexer']+'.py')), scenario['lexer'])
            Parser = (getattr(load(output / (scenario['parser']+'.py')), scenario['parser'])
                      if scenario['parser'] else None)
            oracle = self.root / ('oracle'+str(index))
            oracle.mkdir()
            for name, content in scenario['vocabularies'].items():
                path = oracle / name
                path.write_text(content)
                with self.subTest(scenario=index, vocabulary=name):
                    self.assertEqual(read_vocabulary(path), read_vocabulary(output / name))
            if scenario['parser'] and len(scenario['generate']) > 1:
                # Consume an actual ANTLR .tokens fixture rather than only
                # feeding our own writer back into the reader.
                (path,) = generate(fixtures / (scenario['parser']+'.g4'), oracle / 'generated',
                                   library_dirs=[oracle])
                Parser = getattr(load(path), scenario['parser'])
            for case in scenario['cases']:
                with self.subTest(scenario=index, input=case['input']):
                    stream = CommonTokenStream(Lexer(InputStream(case['input'])))
                    recognizer = Parser(stream) if Parser else None
                    if 'error' in case:
                        with self.assertRaises(SyntaxError):
                            if recognizer:
                                recognizer.start()
                            stream.fill()
                    else:
                        if recognizer:
                            tree = recognizer.start().toStringTree(recog=recognizer)
                            self.assertEqual(case['tree'], tree)
                        stream.fill()
                        self.assertEqual(case['tokens'], [
                            [t.type, t.text, t.line, t.column, t.start, t.stop, t.channel]
                            for t in stream.tokens])


if __name__ == '__main__':
    unittest.main()
