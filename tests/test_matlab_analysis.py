"""Check AST structure and dataflow independently of printed example output."""
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream
from antlr4py import generate


class MatlabAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.output = tempfile.TemporaryDirectory()
        generate(cls.root / 'grammars/matlab61.g4', cls.output.name, visitor=True)
        sys.path[:0] = [cls.output.name, str(cls.root)]
        cls.lexer = importlib.import_module('matlab61Lexer').matlab61Lexer
        cls.parser = importlib.import_module('matlab61Parser').matlab61Parser
        cls.ast_module = importlib.import_module('examples.matlab_ast')
        cls.semantics = importlib.import_module('examples.matlab_semantics')

    @classmethod
    def tearDownClass(cls):
        for path in (cls.output.name, str(cls.root)):
            sys.path.remove(path)
        for name in ('matlab61Lexer', 'matlab61Parser', 'matlab61Visitor',
                     'examples.matlab_ast', 'examples.matlab_semantics'):
            sys.modules.pop(name, None)
        cls.output.cleanup()

    def ast(self, source):
        parser = self.parser(CommonTokenStream(self.lexer(InputStream(source))))
        return self.ast_module.AstBuilder().visit(parser.file_())

    def analyze(self, source, **options):
        analyzer = self.semantics.SemanticAnalyzer(**options)
        diagnostics = analyzer.analyze(self.ast(source))
        return analyzer, diagnostics

    def test_ast_discards_grammar_wrappers_and_preserves_precedence(self):
        ast = self.ast('x = 1 + 2*3;')
        assignment = ast.children[0]
        self.assertEqual((ast.kind, assignment.kind), ('Program', 'Assign'))
        target, addition = assignment.children
        self.assertEqual((target.kind, target.value), ('Name', 'x'))
        self.assertEqual((addition.kind, addition.value), ('Binary', '+'))
        self.assertEqual(addition.children[1].value, '*')
        self.assertEqual(addition.children[1].children[1].value, '3')
        self.assertNotIn('eostmt', str(ast.to_dict()))

    def test_matrix_columns_ranges_handles_and_suffixes(self):
        ast = self.ast("x=[1 -2]; f=@sin; y=feval(f,x(1:end)); s={'can''t'}; z=s{1};")
        matrix = ast.children[0].children[1]
        self.assertEqual([n.kind for n in matrix.children[0].children], ['Number', 'Unary'])
        self.assertEqual(ast.children[1].children[1].kind, 'Handle')
        application = ast.children[2].children[1]
        self.assertEqual(application.kind, 'Apply')
        self.assertEqual(application.children[2].children[1].kind, 'Range')
        cell = ast.children[3].children[1]
        self.assertEqual(cell.children[0].children[0].value, "can't")
        self.assertEqual(ast.children[4].children[1].kind, 'CellIndex')

    def test_rhs_is_checked_before_target_is_defined(self):
        analyzer, diagnostics = self.analyze('x = x + 1;')
        self.assertEqual([d.code for d in diagnostics], ['UNDEFINED_NAME'])
        self.assertEqual((diagnostics[0].line, diagnostics[0].column), (1, 5))
        self.assertEqual(analyzer.defined, {'x'})

    def test_if_merges_definite_and_possible_assignments(self):
        analyzer, diagnostics = self.analyze('x=1; if x>0\ny=2;\nend\nz=y;')
        self.assertEqual([d.code for d in diagnostics], ['POSSIBLY_UNASSIGNED'])
        self.assertEqual(analyzer.defined, {'x', 'z'})
        self.assertIn('y', analyzer.possible)
        _, diagnostics = self.analyze('x=1; if x>0\ny=2;\nelse\ny=3;\nend\nz=y;')
        self.assertEqual(diagnostics, [])

    def test_elseif_does_not_inherit_another_branch_bindings(self):
        _, diagnostics = self.analyze('x=1; if x>0\ny=2;\nelseif y>0\ny=3;\nelse\ny=4;\nend\nz=y;')
        self.assertEqual([d.code for d in diagnostics], ['UNDEFINED_NAME'])
        _, diagnostics = self.analyze('x=1; if x>0\ny=1;\nelseif x<0\ny=2;\nelse\ny=3;\nend\nz=y;')
        self.assertEqual(diagnostics, [])

    def test_commands_are_literal_arguments_and_functions_are_configurable(self):
        _, diagnostics = self.analyze('disp hello; f=@sin; x=feval(f,pi);')
        self.assertEqual(diagnostics, [])
        _, diagnostics = self.analyze('f=@my_function;')
        self.assertEqual([d.code for d in diagnostics], ['UNKNOWN_FUNCTION'])
        _, diagnostics = self.analyze('f=@my_function;', functions={'my_function'})
        self.assertEqual(diagnostics, [])

    def test_dynamic_workspace_operations_are_reported(self):
        for source in ("load data.mat;", "x=eval('a');"):
            with self.subTest(source=source):
                _, diagnostics = self.analyze(source)
                self.assertEqual([d.code for d in diagnostics], ['UNSUPPORTED_WORKSPACE_EFFECT'])

    def test_unsupported_ast_syntax_is_not_silently_skipped(self):
        for source in ('for x=1:3\ny=x;\nend\n', 'x(1)=2;', '[a,b]=size(x);',
                       'function f()\nx=1;\n'):
            with self.subTest(source=source), self.assertRaises(self.ast_module.UnsupportedSyntax):
                self.ast(source)

    def test_analyzer_can_be_reused_without_leaking_symbols(self):
        analyzer = self.semantics.SemanticAnalyzer()
        self.assertEqual(analyzer.analyze(self.ast('x=1;')), [])
        self.assertEqual([d.code for d in analyzer.analyze(self.ast('y=x;'))], ['UNDEFINED_NAME'])

    def test_readme_samples_and_cli_exit_status(self):
        analyzer, diagnostics = self.analyze((self.root/'examples/signal_analysis.m').read_text())
        self.assertEqual(diagnostics, [])
        self.assertEqual(len(analyzer.defined), 5)
        _, diagnostics = self.analyze((self.root/'examples/semantic_errors.m').read_text())
        self.assertEqual([d.code for d in diagnostics], ['UNDEFINED_NAME', 'POSSIBLY_UNASSIGNED'])
        # Launch the CLI against this test's freshly generated package.
        with tempfile.TemporaryDirectory() as work:
            package = Path(work)/'generated'
            package.mkdir()
            for source in Path(self.output.name).glob('*.py'):
                (package/source.name).write_bytes(source.read_bytes())
            (package/'__init__.py').write_text('')
            code = ('import sys; sys.path[:0] = ' + repr([work, str(self.root)]) + '; '
                    'from examples.analyze_matlab import main; raise SystemExit(main())')
            for source, status in (('signal_analysis.m', 0), ('semantic_errors.m', 1)):
                result = subprocess.run([sys.executable, '-I', '-c', code,
                                         str(self.root/'examples'/source)], capture_output=True, text=True)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
