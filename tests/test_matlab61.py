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

    def descendants(self, node, name):
        result = [node] if type(node).__name__ == name else []
        for child in getattr(node, 'children', None) or []:
            result.extend(self.descendants(child, name))
        return result

    def test_matrix_whitespace_changes_column_count(self):
        cases = {
            '[1 -2]': ['1', '-2'],
            '[1 - 2]': ['1-2'],
            '[1- 2]': ['1-2'],
            '[1 +2]': ['1', '+2'],
            '[1 + 2]': ['1+2'],
            '[1 ~2]': ['1', '~2'],
            '[a (b + c)]': ['a', '(b+c)'],
            '[f(1, 2) -3]': ['f(1,2)', '-3'],
            "['a' 'b']": ["'a'", "'b'"],
            '[1 .5]': ['1', '.5'],
            '[1 ...\n2]': ['1', '2'],
            '[1 ...\n -2]': ['1', '-2'],
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                tree = self.parse('x = ' + source + ';')
                row = self.descendants(tree, 'Array_rowContext')[0]
                self.assertEqual([e.getText() for e in row.expression()], expected)
        self.parse('x = [\n1 2\n3 4\n];')
        self.parse('x = {[1 -2] [3 4]};')
        self.parse('[a b] = size(A);')
        self.parse('function [a b] = f(x)\na=x; b=x;\n')

    def test_named_function_handles(self):
        self.parse('f = @sin;\ny = feval(f, .5);\nc = {@sin @cos};\n')
        self.parse('function y = apply(f,x)\ny = feval(f,x);\n')

    def test_command_form_arguments_are_not_expressions(self):
        cases = {
            'disp hello world': ['hello', 'world'],
            "disp 'hello world'": ["'hello world'"],
            'load data.mat': ['data.mat'],
            'save -ascii result.txt A': ['-ascii', 'result.txt', 'A'],
            'cd ../folder': ['../folder'],
            'cd /tmp': ['/tmp'],
            'cd ~/work': ['~/work'],
            'dir *.m': ['*.m'],
            'dir *': ['*'],
            'delete data?.mat': ['data?.mat'],
            'disp [1 2]': ['[1', '2]'],
            'clear all': ['all'],
            'clear x y': ['x', 'y'],
            "disp prefix' with space'": ["prefix' with space'"],
            'plot -option': ['-option'],
            'disp ...\n hello': ['hello'],
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                tree = self.parse(source + '\n')
                command = self.descendants(tree, 'Command_statementContext')[0]
                self.assertEqual([arg.getText() for arg in command.COMMAND_ARGUMENT()], expected)
        self.parse("disp hello; x = 1; disp 'goodbye' % comment\n")
        self.parse("!echo hello world\nx = 1;\n")
        for source in ('x + y', 'x - 2', 'x .* y', 'x(1)', 'x = 1'):
            with self.subTest(expression=source):
                tree = self.parse(source + ';')
                self.assertFalse(self.descendants(tree, 'Command_statementContext'))

    def test_end_requires_indexing_context(self):
        self.parse('x=A(end-1); y=A([1 end]); z=C{end}(1);')
        for source in ('x=end;', 'x={end};', 'x=[end];', 'x=(end);'):
            with self.subTest(source=source), self.assertRaises(SyntaxError):
                self.parse(source)

    def test_reject_invalid_adjacency_and_modern_syntax(self):
        for source in ('x=[1(2)3];', 'x=1 2;', 'x=@(a) a+1;',
                       'x="hello";', 'x=a && b;', 'x=s.(name);',
                       'x=1;\nfunction y=f()\ny=1;\n'):
            with self.subTest(source=source), self.assertRaises(SyntaxError):
                self.parse(source)

    def test_loop_jumps_require_a_loop(self):
        for source in ('break;', 'continue;', 'if x\nbreak;\nend\n',
                       'function f()\ncontinue;\n'):
            with self.subTest(source=source), self.assertRaises(SyntaxError):
                self.parse(source)
        self.parse('for k=1:3\ntry\nif k>1\ncontinue;\nend\ncatch\nbreak;\nend\nend\n')

    def test_representative_m_files(self):
        fixtures = Path(__file__).parent / 'fixtures' / 'matlab61'
        for fixture in sorted(fixtures.glob('*.m')):
            with self.subTest(file=fixture.name):
                self.parse(fixture.read_text())

    def test_lexer_reset_clears_matrix_and_command_state(self):
        lexer = self.lexer_type(InputStream('load file.mat'))
        lexer.getAllTokens()
        lexer.inputStream = InputStream('x = [1 -2];')
        types = [t.type for t in lexer.getAllTokens()]
        self.assertIn(lexer.MATRIXSEP, types)
        self.assertNotIn(lexer.COMMAND_ARGUMENT, types)
        lexer.inputStream = InputStream('x=end;')
        self.assertNotIn(lexer.END_INDEX, [t.type for t in lexer.getAllTokens()])

    def test_final_statement_without_newline_and_invalid_input(self):
        self.parse('x = 1')
        for text in ('x = ;\n', 'if x\ny=1;\n', "x = 'unterminated\n"):
            with self.subTest(text=text), self.assertRaises(SyntaxError):
                self.parse(text)


if __name__ == '__main__':
    unittest.main()
