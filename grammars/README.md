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

## Remaining limits

This is a syntax parser, not a MATLAB interpreter or an authoritative MATLAB
6.1 specification. Tests exercise representative examples without comparison
against a licensed MATLAB 6.1 installation.

Whitespace in matrices still needs fuller lexical treatment. For example,
`[1 -2]` is read as one subtraction expression rather than two columns;
`[1, -2]` expresses the intended columns. Adjacency can also be too permissive.
Quote disambiguation is a practical heuristic, not a full MATLAB lexical model.

Command-form calls such as `disp hello`, dynamic field names, function handles,
class-directory semantics, and exhaustive version-specific syntax are outside
this copy's tested coverage. `end` is accepted as an expression atom and is not
restricted to indexing by a semantic check. Assignment validity, loop-only
`break`/`continue`, symbol resolution, array dimensions, and other semantic rules
are not validated. Nested functions and newer MATLAB syntax are not targets.

Run the focused regression suite:

```sh
python -m unittest discover -s tests -p test_matlab61.py -v
```
