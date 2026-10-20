"""Executable coverage for the extended, explicitly partial MATLAB grammar."""
import importlib
from pathlib import Path
import sys
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4py import generate


class Matlab61Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = tempfile.TemporaryDirectory()
        generate(Path(__file__).resolve().parents[1] / 'grammars' / 'matlab61.g4', cls.output.name)
        sys.path.insert(0, cls.output.name)
        cls.lexer_type = importlib.import_module('matlab61Lexer').matlab61Lexer
        cls.parser_type = importlib.import_module('matlab61Parser').matlab61Parser

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(cls.output.name)
        for name in ('matlab61Lexer', 'matlab61Parser'):
            sys.modules.pop(name, None)
        cls.output.cleanup()

    def parse(self, text):
        lexer = self.lexer_type(InputStream(text))
        parser = self.parser_type(CommonTokenStream(lexer))
        tree = parser.file_()
        self.assertEqual(parser.getNumberOfSyntaxErrors(), 0)
        return tree

    def tokens(self, text):
        lexer = self.lexer_type(InputStream(text))
        return [(lexer.symbolicNames[t.type], t.text) for t in lexer.getAllTokens()]

    def test_comments_continuation_and_numbers(self):
        self.parse('% comment\nx = .5 + ... ignored text\n 1.; % trailing\ny = 1e-3 + 2i;\nz = 1.*2 + 1./2 + 1.^2;\n')
        self.assertEqual(self.tokens("1.*2 1.' .5 1."), [
            ('CONSTANT', '1'), ('ARRAYMUL', '.*'), ('CONSTANT', '2'),
            ('CONSTANT', '1'), ('NCTRANSPOSE', ".'"),
            ('CONSTANT', '.5'), ('CONSTANT', '1.')])

    def test_quote_disambiguation(self):
        self.parse("x = 'can''t';\ny = A';\nz = A.';\nw = A'';\nc = {'one', 'two'};\ns = ['one' 'two'];\n")
        self.assertEqual(self.tokens("A' + 'hello'"), [
            ('IDENTIFIER', 'A'), ('TRANSPOSE', "'"), ('PLUS', '+'),
            ('STRING_LITERAL', "'hello'")])
        lexer = self.lexer_type(InputStream('A'))
        lexer.getAllTokens()
        lexer.inputStream = InputStream("'hello'")
        self.assertEqual(lexer.nextToken().type, lexer.STRING_LITERAL)

    def test_cells_fields_and_index_end(self):
        self.parse("C = {1, 2; 3, 4};\nx = C{1,2};\ns.field = x;\ny = s.field(1:end-1);\nA(:,end) = C{1};\n[a,b] = size(A);\n")

    def test_control_flow(self):
        self.parse('''switch x
case 1
    y = 2;
case {2,3}
    y = 4;
otherwise
    y = 0;
end
try
    y = f(x);
catch
    y = -1;
end
for k = 1:2:9
    if k > 3
        continue;
    elseif k == 2
        break;
    else
        y = y + k;
    end
end
while y < 10
    y = y + 1;
end
''')

    def test_function_files_and_subfunctions(self):
        for source in (
            'function y = square(x)\ny = x^2;\n',
            'function [a,b] = pair(x)\na=x; b=x+1;\nend\n',
            'function y = f(x)\ny=g(x);\nfunction z=g(x)\nz=x+1;\n',
        ):
            with self.subTest(source=source):
                self.parse(source)

    def test_precedence_and_associativity(self):
        tree = self.parse('x = -2^2 + 3*4^2;')
        def descendants(node, name):
            found = [node] if type(node).__name__ == name else []
            for child in getattr(node, 'children', None) or []:
                found.extend(descendants(child, name))
            return found
        unary = descendants(tree, 'Unary_expressionContext')
        negative = next(node for node in unary if node.getText() == '-2^2')
        self.assertEqual(negative.unary_expression().power_expression().getText(), '2^2')
        power = next(node for node in descendants(tree, 'Power_expressionContext') if node.getText() == '4^2')
        self.assertEqual(power.postfix_expression().getText(), '4')
        chained = self.parse('x = 2^3^2;')
        powers = descendants(chained, 'Power_expressionContext')
        self.assertTrue(any(len(node.signed_postfix()) == 2 for node in powers))

    def test_final_statement_without_newline_and_invalid_input(self):
        self.parse('x = 1')
        for text in ('x = ;\n', 'if x\ny=1;\n', "x = 'unterminated\n"):
            with self.subTest(text=text), self.assertRaises(SyntaxError):
                self.parse(text)


if __name__ == '__main__':
    unittest.main()
