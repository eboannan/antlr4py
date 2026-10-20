"""Build a MATLAB AST and run the example semantic analyzer."""
import argparse
import json
from pathlib import Path

from antlr4 import CommonTokenStream, FileStream
from generated.matlab61Lexer import matlab61Lexer
from generated.matlab61Parser import matlab61Parser
from .matlab_ast import AstBuilder, UnsupportedSyntax
from .matlab_semantics import FUNCTIONS, SemanticAnalyzer


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('file', nargs='?', type=Path,
                           default=Path(__file__).with_name('signal_analysis.m'))
    arguments.add_argument('--ast', type=Path, help='write the AST as JSON')
    arguments.add_argument('--function', action='append', default=[],
                           help='add a known external function name (repeatable)')
    args = arguments.parse_args()
    try:
        parser = matlab61Parser(CommonTokenStream(matlab61Lexer(FileStream(str(args.file), encoding='utf-8'))))
        ast = AstBuilder().visit(parser.file_())
    except (OSError, SyntaxError, UnsupportedSyntax) as error:
        print(f'{args.file}: {error}')
        return 2
    if args.ast:
        args.ast.write_text(json.dumps(ast.to_dict(), indent=2) + '\n', encoding='utf-8')
    analyzer = SemanticAnalyzer(functions=FUNCTIONS | set(args.function))
    diagnostics = analyzer.analyze(ast)
    print(f'AST: {len(ast.children)} top-level statements')
    print('Definitely assigned: ' + (', '.join(sorted(analyzer.defined)) or '(none)'))
    for diagnostic in diagnostics:
        print(f'{args.file.name}:{diagnostic}')
    if not diagnostics:
        print('Semantic checks: OK (example subset)')
    return 1 if diagnostics else 0


if __name__ == '__main__':
    raise SystemExit(main())
