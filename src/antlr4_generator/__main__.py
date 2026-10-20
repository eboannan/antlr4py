import argparse
import sys
from pathlib import Path

from . import GrammarError, generate, __version__
from .grammar import parse_grammar


def dependency_order(paths, encoding, options):
    sources = {path: parse_grammar(Path(path).read_text(encoding=encoding)) for path in paths}
    providers = {}
    for path, source in sources.items():
        providers[source.name] = path
        if source.kind == 'combined':
            providers[source.name+'Lexer'] = path
    ordered, active, visited = [], set(), set()
    def visit(path):
        if path in active:
            raise GrammarError('Token-vocabulary dependency cycle among input grammars')
        if path not in visited:
            active.add(path)
            vocab = options.get('tokenVocab', sources[path].token_vocab)
            dependency = providers.get(vocab)
            if dependency is not None:
                visit(dependency)
            active.remove(path)
            visited.add(path)
            ordered.append(path)
    for path in paths:
        visit(path)
    return ordered


def main():
    parser = argparse.ArgumentParser(description='Experimental Python-only ANTLR subset generator')
    parser.add_argument('grammar', nargs='+', help='combined, lexer, or parser .g4 grammars')
    parser.add_argument('-o', '--output-dir', default='.')
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('-version', '--version', action='version', version=__version__)
    parser.add_argument('-encoding', '--encoding', default='utf-8')
    parser.add_argument('-D', dest='options', action='append', default=[], metavar='name=value')
    parser.add_argument('-package', dest='package')
    parser.add_argument('-Xexact-output-dir', action='store_true', help='output is always placed directly in -o')
    parser.add_argument('-lib', '--library-dir', action='append', default=[],
                        help='search directory for imports and token vocabularies (repeatable)')
    visitors = parser.add_mutually_exclusive_group()
    visitors.add_argument('-visitor', '--visitor', dest='visitor', action='store_true')
    visitors.add_argument('-no-visitor', dest='visitor', action='store_false')
    listeners = parser.add_mutually_exclusive_group()
    listeners.add_argument('-listener', dest='listener', action='store_true')
    listeners.add_argument('-no-listener', '--no-listener', dest='listener', action='store_false')
    parser.set_defaults(visitor=False, listener=True)
    args = parser.parse_args()
    options = {}
    for option in args.options:
        name, separator, value = option.partition('=')
        if not separator or not name or not value:
            parser.error('-D requires name=value')
        options[name] = value
    try:
        paths = []
        for grammar in dependency_order(args.grammar, args.encoding, options):
            paths.extend(generate(grammar, args.output_dir, overwrite=args.overwrite,
                         library_dirs=args.library_dir, visitor=args.visitor, listener=args.listener,
                         encoding=args.encoding, options=options, package=args.package))
    except (GrammarError, OSError, LookupError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    for path in paths:
        print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
