# MATLAB grammars

- `matlab.g4` is the original uploaded grammar, preserved unchanged.
- `matlab61.g4` is an extended Python-target derivative for common MATLAB 6.1
  syntax. Its name states the target, not a certification of completeness.
  The original BSD license and attribution remain in both files.

Generate and use the extended grammar from the repository root:

```sh
python -m antlr4py grammars/matlab61.g4 -o generated -package generated
```

```python
from antlr4 import CommonTokenStream, InputStream
from generated.matlab61Lexer import matlab61Lexer
from generated.matlab61Parser import matlab61Parser

source = "C = {1, 2};\nx = C{end};\ny = .5 + x^2; % comment\n"
parser = matlab61Parser(CommonTokenStream(matlab61Lexer(InputStream(source))))
tree = parser.file_()
print(tree.toStringTree(recog=parser))
```

## Added or corrected

- `%` comments, `...` continuation lines, and CR/LF line endings.
- `switch`/`case`/`otherwise`, `try`/`catch`, `continue`, and `persistent`.
- Cell literals, cell indexing, static structure fields, chained indexing,
  colon indexing, and `end` in index expressions.
- Function declarations reachable from `file_`, multiple output arguments,
  and function files with subfunctions, with or without explicit function `end`.
- Conjugate transpose `'`, nonconjugate transpose `.'`, and quoted character
  arrays with doubled-quote escapes. Python lexer members distinguish a string
  opener from a transpose using the preceding token and matrix/cell context.
- Leading/trailing decimal points, exponents, and imaginary-number suffixes;
  elementwise operators remain distinct from a trailing decimal point.
- Power above unary signs and multiplication, left-to-right chained powers,
  and colon above relational and logical operators.
- Final statements without a trailing newline; restricted assignment targets.
- Significant matrix/cell whitespace, command-form calls and named function
  handles; `end` restricted to indexing and loop jumps restricted to loops.

## Gap audit and current limits

The [coverage audit](MATLAB61_AUDIT.md) records the concrete fixes, syntax
inventory, intentionally excluded newer syntax, and remaining verification work.
The extended copy now handles significant matrix whitespace, command-form calls,
named function handles, shell escapes, indexing-only `end`, and loop-only
`break`/`continue`. The original uploaded copy is still unchanged.

For example, `[1 -2]` produces two columns, whereas `[1 - 2]` produces one
subtraction expression. `disp hello` is represented as a command with a raw
argument, rather than as an arithmetic expression.

This is a syntax parser, not a MATLAB interpreter or a certified MATLAB 6.1
specification. No archived 6.1 manual, reference installation, or independent
period-correct corpus was available for this audit. Command/quote ambiguities
and uncommon historical syntax still need that comparison. Runtime semantics
such as array dimensions and variable/function resolution are outside scope.

Run the focused regression suite:

```sh
python -m unittest discover -s tests -p test_matlab61.py -v
```
