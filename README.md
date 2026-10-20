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
| Parse a MATLAB file | Follow the [MATLAB example](#parse-a-matlab-file). |
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

## Included grammars

The [grammars folder](grammars/README.md) contains the original MATLAB grammar
and an extended `matlab61.g4` copy with usage instructions and known limits.

## Parse a MATLAB file

The included [signal_analysis.m](examples/signal_analysis.m) demonstrates matrix
whitespace, indexing with `end`, a function handle, and command-form calls:

```matlab
samples = [1 -2 3 .5];
signal = samples(1:end-1);
gain = @sin;
result = feval(gain, signal);
last = result(end);

if last > 0
    disp 'positive sample'
else
    disp 'nonpositive sample'
end
```

From the repository root, generate a Python parser and visitor using
[matlab61.g4](grammars/matlab61.g4), then parse the `.m` file:

```sh
python -m antlr4py grammars/matlab61.g4 -o generated -package generated --visitor
python -m examples.parse_matlab examples/signal_analysis.m
```

Expected output:

```text
Parsed: signal_analysis.m
Assignments (5): samples, signal, gain, result, last
```

The [Python example](examples/parse_matlab.py) reads the file, constructs a parse
tree, and visits assignments to collect their targets. To inspect the full tree:

```sh
python -m examples.parse_matlab examples/signal_analysis.m --tree
```

To parse your own file:

```sh
python -m examples.parse_matlab path/to/your_script.m
```

This converts MATLAB source into a **parse tree**, not executable Python. It
does not execute the script or translate its calculations. A translator would
need additional visitor logic. The grammar's [coverage audit](grammars/MATLAB61_AUDIT.md)
describes the remaining MATLAB 6.1 verification limits. If regenerating existing
parser files, add `--overwrite` to the generation command.

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
