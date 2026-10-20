# antlr4py

A Python implementation of the ANTLR 4 generator, targeting **Python only**.
Turn `.g4` grammars into lexers, parsers, visitors, and listeners using Python
3.10 or later. Installation, generation, and parsing need no Java, JVM, JARs,
Maven, or external generator process.

The only runtime dependency is `antlr4-python3-runtime==4.13.2`, installed by
pip. Generated recognizers also use helpers supplied by `antlr4py`.

**Status:** experimental, version 0.11.0a1. The planned Python feature milestones
are implemented, with reference-based regression tests. This is not certified
as a drop-in replacement for every ANTLR grammar. See [compatibility](COMPATIBILITY.md).

## Quick-pick onboarding

Pick your starting point:

| I want to… | Start here |
| --- | --- |
| Try a working parser | Follow the two-minute example below. |
| Generate my own grammar | Run `antlr4py MyGrammar.g4 -o generated --visitor`. |
| Generate from Python | Use `from antlr4py import generate` below. |
| Contribute | Install the checkout and run the test command below. |

### 1. Install this checkout

```sh
cd antlr4py
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install .
```

The package has not been published to PyPI. Install this checkout or its wheel;
a bare `pip install antlr4py` is not yet a verified installation source.

### 2. Generate and run a parser

From the repository root:

```sh
python -m antlr4py examples/Numbers.g4 -o generated -package generated
python -m examples.parse_numbers
```

Expected output:

```text
(start 12 , 34 , 56 <EOF>)
```

The included grammar recognizes a comma-separated list of integers:

```antlr
grammar Numbers;
start: INT (',' INT)* EOF;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
```

### Python API

```python
from antlr4py import generate

lexer_path, parser_path = generate(
    "examples/Numbers.g4", "generated", visitor=True, package="generated"
)
```

Existing files are protected. Use `--overwrite` or `overwrite=True` to replace
them. The earlier `antlr4_generator` API and `antlr4-python` command remain
available for existing callers.

## What it supports

- Combined and separate grammars, imports, token vocabularies, and library paths.
- Adaptive prediction, direct left recursion, precedence, and associativity.
- Lexer modes, commands, recursive lexer rules, Unicode properties, and case folding.
- Typed contexts, labels, visitors, listeners, Python actions, and predicates.
- Rule arguments, return values, exception handlers, and optional error recovery.

Strict parsing raises `SyntaxError` by default. Pass `recover=True` when
constructing recognizers to enable ANTLR-style recovery. Grammar actions execute
Python code, so use grammars you trust.

See [full usage and grammar examples](USAGE.md) and
[compatibility and boundaries](COMPATIBILITY.md).

## Develop and test

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Tests use bundled reference snapshots and require no Java. This repository
excludes the upstream Java generator, build system, dependencies, and oracle
regeneration scripts. Grammars that describe Java syntax are test data only.

To build an installable wheel and source distribution:

```sh
python -m pip install build
python -m build
```

## License

BSD-3-Clause, with the Unicode data license for bundled Unicode tables.
See [LICENSE.txt](LICENSE.txt) and [UNICODE-LICENSE.txt](UNICODE-LICENSE.txt).
