"""Smoke-test an installed distribution, independently of the checkout."""
from importlib import import_module, metadata, resources
from pathlib import Path
import subprocess
import sys
import tempfile

from antlr4 import CommonTokenStream, InputStream
from antlr4py import __version__, generate


def main():
    assert __version__ == metadata.version('antlr4py')
    data = resources.files('antlr4_generator')
    for name in ('unicode15.json', 'unicode_properties.json'):
        assert data.joinpath(name).read_bytes(), name
    for command in ([sys.executable, '-m', 'antlr4py'],
                    [sys.executable, '-m', 'antlr4_generator'],
                    ['antlr4py'], ['antlr4-python']):
        result = subprocess.run(command + ['--version'], check=True,
                                capture_output=True, text=True)
        assert result.stdout.strip() == __version__, result.stdout
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        grammar = root / 'Smoke.g4'
        grammar.write_text(r'''grammar Smoke;
start: WORD EOF;
WORD: [\p{L}]+;
WS: [ \t\r\n]+ -> skip;
''', encoding='utf-8')
        generate(grammar, root, visitor=True, listener=True)
        sys.path.insert(0, directory)
        try:
            lexer = import_module('SmokeLexer').SmokeLexer(InputStream('hello'))
            parser = import_module('SmokeParser').SmokeParser(CommonTokenStream(lexer))
            assert parser.start().toStringTree(recog=parser) == '(start hello <EOF>)'
            import_module('SmokeVisitor')
            import_module('SmokeListener')
        finally:
            sys.path.remove(directory)
    print(f'Installed antlr4py {__version__}: OK')


if __name__ == '__main__':
    main()
