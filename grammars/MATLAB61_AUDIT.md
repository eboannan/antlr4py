# MATLAB 6.1 syntax coverage audit

Scope: `matlab61.g4`, a Python-target syntax grammar. `matlab.g4` remains the
unaltered uploaded starting point. This audit distinguishes implemented syntax,
version boundaries, semantic responsibilities, and missing historical evidence.
It is not a claim of exhaustive MATLAB 6.1 conformance.

## Concrete gaps closed

| Finding in the earlier extended copy | Correction and evidence |
| --- | --- |
| `[1 -2]` became subtraction rather than two columns | Significant `MATRIXSEP` tokens distinguish `[1 -2]`, `[1 - 2]`, `[1- 2]`, signed columns, nested literals, and decimal columns. Tests inspect the resulting expression list. |
| Adjacent expressions were accepted without any delimiter | Array rows now require commas or significant whitespace; malformed adjacency is rejected. |
| Whitespace in return/assignment lists broke when spaces became tokens | Both `[a b] = f()` and `function [a b] = f(x)` accept significant whitespace. |
| Matrix columns joined by an ellipsis lost their separator | Continuation actions preserve column separation, including an unindented following line. |
| `disp hello`, `load file.mat`, and `save -ascii out.txt A` failed | Command statements preserve raw argument token text, including quoted spaces, options, paths, and adjacent quoted/unquoted segments. Tests inspect arguments. |
| `clear` was incorrectly reserved as syntax | It is now an ordinary identifier, allowing both command and parenthesized invocation forms. |
| Named function handles were absent | `@sin`, handles in cells, and passing handles to `feval` parse. |
| `end` was accepted anywhere as an expression | The lexer distinguishes `END_INDEX` only within an indexing delimiter context; standalone and literal-only uses are rejected. |
| `break` and `continue` were accepted outside loops | Parser predicates require an enclosing `for`/`while`, stopping at function boundaries. |
| Scripts could contain later-version local function definitions | The entry rule separates script files from function files with subfunctions. |
| Lexer reuse could leak command/delimiter state | `reset()` clears all contextual state; regression tests reuse the same lexer. |
| Shell escape statements were absent | `!` at a statement boundary captures the remainder of its line as syntax, without executing it. |

## Syntax inventory

| Area | Current coverage |
| --- | --- |
| Lexical forms | ASCII identifiers, reserved words, quoted character arrays with doubled quotes, decimal/exponent/imaginary literals, `%` comments, `...` continuations, CR/LF/CRLF. |
| Operators | Scalar/elementwise arithmetic, both transposes, unary signs/negation, comparisons, `&`, `|`, and colon. Tests inspect power/unary precedence and chained-power structure. |
| Arrays | Empty/nonempty matrices and cells, comma/space columns, newline/semicolon rows, nested literals. |
| References | Parenthesis indexing/calls, cell indexing, static structure fields, chained suffixes, colon and index `end`. |
| Assignments | Identifier/index/field targets, multiple output targets, empty-array RHS. |
| Control flow | `if`/`elseif`/`else`, `switch`/`case`/`otherwise`, `for`, `while`, `try`/`catch`, `break`, `continue`, `return`. |
| Declarations/files | `global`, `persistent`, scripts, functions, multiple outputs, subfunctions, explicit/implicit function endings. |
| Calls | Parenthesized calls, zero-argument identifiers, command calls, named function handles, shell escapes. |

The focused tests contain positive and negative examples, token checks,
parse-tree checks, reset checks, and two representative `.m` files in
`tests/fixtures/matlab61/`. They do not execute MATLAB code.

## Version boundaries

The target remains the older language, rather than current MATLAB. The grammar
intentionally rejects anonymous functions (`@(x) ...`), dynamic field expressions
(`s.(name)`), `&&`/`||`, double-quoted string arrays, and script-local function
definitions. Nested functions, `classdef`, and later argument/declaration blocks
are also outside scope. These boundary choices still need a review against an
archived 6.1 language manual; rejection tests alone are not historical evidence.

An earlier response listed dynamic field names alongside missing syntax without
checking their release history. They are not being added merely because modern
MATLAB supports them.

## What remains to establish completeness

1. **Historical specification review.** A MATLAB 6.1 language manual and release
   notes were not available in this environment. Review the inventory against
   those sources, including command/operator ambiguities, whitespace before
   indexing, empty/trailing matrix separators, continuation/linebreak edge
   cases, legal numeric forms, and function-ending rules.
2. **Independent implementation comparison.** No MATLAB 6.1 installation was
   available. Run an appropriately licensed reference on a versioned corpus of
   accepted and rejected files; add regressions for every discrepancy. Modern
   MATLAB or Octave can be supplemental comparisons, but cannot certify 6.1.
3. **Real-file corpus.** The two checked-in files are synthetic examples, not a
   broad independently sourced MATLAB 6.1 corpus. Add licensed period-correct
   scripts, functions, private functions, and class-directory method files.

In particular, command detection uses token/spacing rules, and apostrophe
classification uses delimiter/expression context. Their tested cases work;
untested ambiguous forms must not be described as fully verified.

## Responsibilities outside this grammar

Parsing does not evaluate expressions, resolve variables versus function names,
select class methods, check array dimensions/index bounds, validate assignment
values, implement `eval`/commands, or execute shell escapes. Those are separate
semantic/runtime responsibilities, not missing production rules. Class-directory
and private-function visibility also require filesystem/symbol information.

## Reproduce

```sh
python -m pip install .
python -m unittest discover -s tests -p test_matlab61.py -v
python -m unittest discover -s tests -v
```
