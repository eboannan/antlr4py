"""Parse a MATLAB source file and summarize assignments without executing it."""
import argparse
from pathlib import Path

from antlr4 import CommonTokenStream, FileStream
from generated.matlab61Lexer import matlab61Lexer
from generated.matlab61Parser import matlab61Parser
from generated.matlab61Visitor import matlab61Visitor


class AssignmentCollector(matlab61Visitor):
    def __init__(self):
        self.targets = []

    def visitAssignment_expression(self, ctx):
        self.targets.append(ctx.assignment_target().getText())
        return self.visitChildren(ctx)


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('file', nargs='?', type=Path,
                           default=Path(__file__).with_name('signal_analysis.m'))
    arguments.add_argument('--tree', action='store_true', help='also print the full parse tree')
    args = arguments.parse_args()

    lexer = matlab61Lexer(FileStream(str(args.file), encoding='utf-8'))
    parser = matlab61Parser(CommonTokenStream(lexer))
    tree = parser.file_()
    collector = AssignmentCollector()
    collector.visit(tree)

    print(f'Parsed: {args.file.name}')
    print(f'Assignments ({len(collector.targets)}): {", ".join(collector.targets)}')
    if args.tree:
        print(tree.toStringTree(recog=parser))


if __name__ == '__main__':
    main()
