# antlr4py

A Python implementation of the ANTLR 4 generator, targeting **Python only**.
Turn `.g4` grammars into lexers, parsers, visitors, and listeners using Python
3.10 or later. Installation, generation, and parsing need no Java, JVM, JARs,
Maven, or external generator process.

The only runtime dependency is `antlr4-python3-runtime==4.13.2`, installed by
pip. Generated recognizers also use helpers supplied by `antlr4py`.

**Status:** experimental, version 0.11.0a1. The planned Python feature milestones
are implemented, with reference-based regression tests. This is not certified
as a drop-in replacement for every ANTLR grammar. See [compatibility](https://github.com/eboannan/antlr4py/blob/main/COMPATIBILITY.md).

## Quick-pick onboarding

Pick your starting point:

| I want to… | Start here |
| --- | --- |
| Try a working parser | Follow the two-minute example below. |
| Build an AST and check names | Follow the [AST and semantic analysis example](#build-an-ast-and-run-semantic-analysis). |
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

See [full usage and grammar examples](https://github.com/eboannan/antlr4py/blob/main/USAGE.md) and
[compatibility and boundaries](https://github.com/eboannan/antlr4py/blob/main/COMPATIBILITY.md).

## Included grammars

The [grammars folder](https://github.com/eboannan/antlr4py/blob/main/grammars/README.md) contains the original MATLAB grammar
and an extended `matlab61.g4` copy with usage instructions and known limits.

## Parse a MATLAB file

The included [signal_analysis.m](https://github.com/eboannan/antlr4py/blob/main/examples/signal_analysis.m) demonstrates matrix
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
[matlab61.g4](https://github.com/eboannan/antlr4py/blob/main/grammars/matlab61.g4), then parse the `.m` file:

```sh
python -m antlr4py grammars/matlab61.g4 -o generated -package generated --visitor
python -m examples.parse_matlab examples/signal_analysis.m
```

Expected output:

```text
Parsed: signal_analysis.m
Assignments (5): samples, signal, gain, result, last
```

The [Python example](https://github.com/eboannan/antlr4py/blob/main/examples/parse_matlab.py) reads the file, constructs a parse
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
need additional visitor logic. The grammar's [coverage audit](https://github.com/eboannan/antlr4py/blob/main/grammars/MATLAB61_AUDIT.md)
describes the remaining MATLAB 6.1 verification limits. If regenerating existing
parser files, add `--overwrite` to the generation command.

## Build an AST and run semantic analysis

The workflow has three stages:

1. `matlab61.g4` generates a parser that produces a **parse tree** with grammar
   rules, separators, and expression structure.
2. [AstBuilder](https://github.com/eboannan/antlr4py/blob/main/examples/matlab_ast.py) visits that tree and produces an
   **abstract syntax tree (AST)** containing meaningful nodes such as `Assign`,
   `Name`, `Binary`, `Matrix`, `Apply`, and `If`. Nodes retain line/column locations.
3. [SemanticAnalyzer](https://github.com/eboannan/antlr4py/blob/main/examples/matlab_semantics.py) walks the AST, tracks assigned
   names, checks references, and merges assignment information across branches.
   It has no dependency on the parser or its grammar-rule classes.

For `x = 1 + 2*3;`, the AST structure is:

```text
Program
  Assign
    Name: x
    Binary: +
      Number: 1
      Binary: *
        Number: 2
        Number: 3
```

Generate the parser and visitor, then build an AST and analyze the sample:

```sh
python -m antlr4py grammars/matlab61.g4 -o generated -package generated --visitor --overwrite
python -m examples.analyze_matlab examples/signal_analysis.m --ast generated/signal_ast.json
```

Expected output:

```text
AST: 6 top-level statements
Definitely assigned: gain, last, result, samples, signal
Semantic checks: OK (example subset)
```

`generated/signal_ast.json` contains the AST as JSON, with node kinds, values,
children, and source locations. Semicolons and grammar-only wrapper rules are
omitted; matrix rows, operator precedence, and control-flow branches are retained.

Try [semantic_errors.m](https://github.com/eboannan/antlr4py/blob/main/examples/semantic_errors.m), which is syntactically valid:

```matlab
% Valid syntax with deliberate semantic errors for the teaching analyzer.
x = missing + 1;
if x > 0
    y = 2;
end
z = y + 1;
```

```sh
python -m examples.analyze_matlab examples/semantic_errors.m
```

Expected output (exit status **1** indicates diagnostics):

```text
AST: 3 top-level statements
Definitely assigned: x, z
semantic_errors.m:2:5: UNDEFINED_NAME: 'missing' is not defined or in the demo's catalog
semantic_errors.m:6:5: POSSIBLY_UNASSIGNED: 'y' is not assigned on every path
```

The right side of an assignment is checked before its target becomes defined.
For `if`/`elseif`/`else`, a name is definitely assigned afterward only if every
branch assigns it. Without an `else`, the analyzer includes the path on which
none of the conditions holds. It conservatively considers all branches possible.

The key Python calls, after constructing `parser` as in the parsing example, are:

```python
from examples.matlab_ast import AstBuilder
from examples.matlab_semantics import SemanticAnalyzer

ast = AstBuilder().visit(parser.file_())
analyzer = SemanticAnalyzer()
for diagnostic in analyzer.analyze(ast):
    print(diagnostic)
```

### Example scope

This is a teaching analyzer with a **closed-world function catalog**. Unknown
names may refer to functions or workspace variables in real MATLAB. Add known
external functions with `--function my_function` (repeatable), or pass a function
set to `SemanticAnalyzer(functions=...)`. The CLI adds to the default catalog;
the Python argument replaces it.

The AST builder supports script assignments to a single plain name, expressions,
matrices/cells, ranges, indexing/fields, named handles, command calls, and
`if`/`elseif`/`else`. Function files, loops, declarations, shell escapes, indexed
assignment targets, and multiple-output assignments raise an explicit
unsupported-syntax error (exit status **2**) rather than being silently skipped.
The grammar itself supports more syntax than this AST example.

`Apply` preserves MATLAB's ambiguity between `f(x)` calls and `A(x)` indexing.
The example checks names without resolving that ambiguity or inferring types,
shapes, function signatures, or field existence. Command arguments remain literal
text; `disp hello` does not read a variable called `hello`. Workspace-changing
operations such as `load`, `clear`, and `eval` produce an explicit diagnostic.
The analyzer does not execute code, evaluate branch conditions, or inspect the
MATLAB workspace/search path. A clean result establishes these limited checks,
not that the program can execute successfully.

## Release preparation

See [RELEASING.md](https://github.com/eboannan/antlr4py/blob/main/RELEASING.md)
for artifact verification and TestPyPI/PyPI upload instructions.

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
See [LICENSE.txt](https://github.com/eboannan/antlr4py/blob/main/LICENSE.txt) and [UNICODE-LICENSE.txt](https://github.com/eboannan/antlr4py/blob/main/UNICODE-LICENSE.txt).
