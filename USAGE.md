# Experimental Python-only ANTLR generator

This is an experimental Python implementation of the ANTLR
generator. Installing it, generating a parser, and running that parser require
Python 3.10+ and **no Java**. It is not a drop-in replacement for ANTLR 4.

Install from this checkout:

```sh
python -m pip install .
```

Save this as `Numbers.g4`:

```antlr
grammar Numbers;
start: INT (',' INT)* EOF;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
```

Generate Python modules:

```sh
python -m antlr4_generator Numbers.g4 -o generated
# Or: antlr4-python Numbers.g4 -o generated
```

Use them from a Python program with `generated` on the import path:

```python
from antlr4 import InputStream, CommonTokenStream
from generated.NumbersLexer import NumbersLexer
from generated.NumbersParser import NumbersParser

parser = NumbersParser(CommonTokenStream(NumbersLexer(InputStream("12, 34, 56"))))
tree = parser.start()
print(tree.toStringTree(recog=parser))
# (start 12 , 34 , 56 <EOF>)
```

Or generate through the API:

```python
from antlr4_generator import generate

lexer_path, parser_path = generate("Numbers.g4", "generated")
```

Output files are protected against accidental overwriting. Pass `--overwrite`
or `overwrite=True` to replace them intentionally. Generated modules depend on
this package's execution helpers and the pinned `antlr4-python3-runtime==4.13.2`.
There is no runtime code generation, JVM bridge, Java download, or subprocess.

## Supported Python target

- Combined grammars and standalone `lexer grammar` / `parser grammar` files.
- `tokenVocab` options, `.tokens` vocabulary output/input, and imports/aliases
  with root-rule overrides and transitive delegate resolution.
- Parser sequences, alternatives, grouping, token/rule references, literals,
  `EOF`, wildcard tokens, negated token sets, and greedy/nongreedy
  `?`, `*`, `+` operators.
- Adaptive prediction for shared-prefix alternatives and decisions that need
  the caller's continuation, including overlapping loop/optional choices.
- Empty parser alternatives. Ambiguous choices follow ANTLR's prediction
  behavior rather than being rejected by an LL(1) check.
- Direct left recursion for binary and postfix operators; prefix operators and
  parentheses in the same rule. Earlier alternatives bind more tightly.
- Left associativity by default, with `<assoc=right>` on recursive binary
  alternatives (including conditional expressions).
- Lexer alternatives, grouped sequences, recursive rule/fragment references,
  optional elements and repetition anywhere in the rule, and nongreedy
  `??`, `*?`, and `+?`.
- Character sets and ranges, negation (`~`), wildcards (`.`), Unicode literals,
  four-digit and braced escapes, Unicode categories/scripts/blocks/binary and
  enumerated properties from ANTLR 4.13.2, and case-insensitive lexer options.
- Lexer `skip`, `more`, `type`, `channel`, `mode`, `pushMode`, and `popMode`
  commands with symbolic arguments, plus token and channel declarations.
- Multiple lexer modes in standalone lexer grammars, longest match across
  rules, and rule-order tie breaking.
  Implicit literal tokens take priority on equal-length matches.
- ANTLR token streams and generic rule contexts with text and tree rendering.
- Typed rule contexts (`Parser.ExprContext`), rule-index constants, scalar/list
  token and rule accessors, generated visitors, and generated listeners.
- Alternative labels, scalar/list element labels, and Python-style rule
  arguments, returns, and locals; return/local initializers can be Python expressions.
- Embedded Python parser/lexer actions and semantic predicates; parser rule
  `@init`/`@after` hooks and grammar header/member blocks.
- Parser rule `catch`/`finally` clauses and dynamic nonlocal attribute access
  (`$rule::attribute`) in actions, predicates, and rule-call arguments.
- Python grammar options, custom recognizer/context bases, keyword escaping,
  arbitrary Python call arguments, persistent closure scopes, and early returns.
- Strict `SyntaxError` parsing by default, with opt-in ANTLR error recovery,
  error listeners/nodes, missing-token insertion, deletion, and resynchronization.

The planned Python-recognizer milestones are implemented. Compatibility is
validated against ANTLR 4.13.2, including a larger Java grammar adapted to Python
Unicode predicates, the repository's expression grammar, and its Python XPath
lexer. This is still an experimental implementation, not a claim of complete
ANTLR tool equivalence. See [the compatibility audit](COMPATIBILITY.md) for the
verified surface, deliberate differences, and guarded cases.
Use an explicit `EOF` in an entry rule to require consumption of the full input.

## Rule contexts, visitors, and listeners

Every parser rule now returns its generated context type. For example,
`parser.start()` returns `NumbersParser.StartContext`. Contexts expose
`getRuleIndex()`, `getText()`, source intervals, and normal parent/child links.
The parser also exposes `RULE_start`, `RULE_expr`, and other rule-index constants.

Named token and rule references get accessors based on their maximum direct
occurrence count in the original grammar:

- A single/optional occurrence uses `ctx.ID()` or `ctx.expr()`, returning a node
  or `None` when absent.
- Repeated occurrences use `ctx.ID()` / `ctx.expr()` for a list, and
  `ctx.ID(i)` / `ctx.expr(i)` for an indexed node or `None` when out of range.
- Explicit `EOF` references get `ctx.EOF()`. Literal-only references do not
  create named token accessors, matching the reference generator.

Listeners are generated by default. Request a visitor with `-visitor`, and
disable either helper with `-no-listener` or `-no-visitor`:

```sh
python -m antlr4_generator Numbers.g4 -visitor --overwrite -o generated
```

```python
from antlr4 import InputStream, CommonTokenStream, ParseTreeWalker
from generated.NumbersLexer import NumbersLexer
from generated.NumbersParser import NumbersParser
from generated.NumbersVisitor import NumbersVisitor
from generated.NumbersListener import NumbersListener

class ReadNumbers(NumbersVisitor):
    def visitStart(self, ctx):
        return [int(node.getText()) for node in ctx.INT()]

class ReportNumbers(NumbersListener):
    def exitStart(self, ctx):
        print(ctx.getText())

parser = NumbersParser(CommonTokenStream(NumbersLexer(InputStream("12,34"))))
tree = parser.start()
print(ReadNumbers().visit(tree))  # [12, 34]
ParseTreeWalker.DEFAULT.walk(ReportNumbers(), tree)
```

Visitors provide `visitRuleName` methods delegating to `visitChildren`.
Listeners provide `enterRuleName` and `exitRuleName`, and also support the
runtime's generic and terminal callbacks. `parser.addParseListener(listener)`
receives callbacks during parsing; `ParseTreeWalker` traverses a completed tree.
Left-recursive expression wrapping retains typed contexts and callback order.

The API equivalents are `generate(..., visitor=True, listener=True)`.
The return value still contains only recognizer paths; helpers are generated
beside them and protected against overwriting. Standalone parsers use
`GrammarNameVisitor.py` and `GrammarNameListener.py`, just like combined
grammars. Standalone lexers do not produce tree helpers. Helper modules work
with package imports and do not require Java.

A grammar whose generated accessor or context name would overwrite a runtime attribute is rejected before output is written. With
`buildParseTrees=False`, child-rule accessors have no stored children to return.

## Labels and rule attributes

Alternative labels select context subclasses and visitor/listener methods:

```antlr
expr: left=expr op='+' right=expr # Add
    | value=INT # Integer;
```

This returns `AddContext` or `IntegerContext`; use `ctx.left`, `ctx.op`,
`ctx.right`, and `ctx.value` directly. `visitAdd` and `visitInteger` dispatch
on these subclasses. All alternatives of a labeled rule must have labels.
Repeated labels such as `items+=expr` collect context objects in a list;
token labels hold runtime token objects. Labels work without stored parse trees.

Rule declarations use Python-style names and optional annotations:

```antlr
start: result=child[3] EOF;
child[n: int] returns [value: int = 0] locals [seen: list = []]
    : head=INT (rest+=INT)*;
```

`parser.child(3)` passes `n` to the returned context. Arguments, returns, and
locals become context attributes. Literal defaults are copied for each context,
including mutable lists. Embedded actions can read and assign these attributes.
Rule-call arguments support Python expressions and calls, including `$n`,
`$result.value`, `int($token.text)`, and ordinary Python locals from earlier
blocks. Return/local initializers such as `items: list = list()` execute for each
context; optional argument defaults remain literal values. Left-recursive rules
support returns/locals; ANTLR itself rejects argument-bearing left-recursive
rules that do not fit its supported recursion patterns.

## Embedded Python actions and semantic predicates

Actions execute at their position in a parser rule, after preceding labels have
been assigned. For example:

```antlr
grammar Values;
start returns [value: int]
    : number=INT EOF {$value = $number.int};
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
```

The result of `parser.start().value` is the parsed integer. Actions support calls,
assignments, loops, conditionals, nested dictionaries, strings, and comments.
`$name` refers to a rule argument, return/local attribute, or element label.
Unlabeled token/rule references also support `$INT.text` and `$child.value`.
Token properties include `text`, `int`, `type`, `line`, `pos`, `channel`, and
`index`. Rule properties include returned attributes, `text`, `start`, `stop`,
`ctx`, and `parser`; `$ctx`, `$text`, `$start`, and `$stop` refer to the current
rule. Python strings and comments keep literal dollar signs unchanged.

`rule @init {...} @after {...}: ...;` runs initialization on entry and the after
hook on successful completion before exit-listener callbacks. Ordinary Python
locals assigned in one action remain available to later actions/hooks in the
same rule invocation. Recursive invocations have separate local state.

A semantic predicate is a Python expression followed by `?`:

```antlr
choice returns [selected: str]
    : {self.enabled}? INT {$selected = 'enabled'}
    | INT {$selected = 'fallback'};
```

Set `parser.enabled` before parsing. Visible predicates participate in adaptive
prediction, including cached decisions; predicates after a token/action also run
at their position as checks. A failed check raises `SyntaxError` in strict mode;
recovery mode reports the failure and recovers from the current rule.
Predicate expressions should have no side
effects: prediction can evaluate them multiple times. Actions never run during
prediction.

Lexer actions and predicates use Python runtime properties directly, for example
`WORD: [a-z]+ {self.text = self.text.upper()};` and
`IDENTIFIER: {self.allow_words}? [a-z]+;`. Lexer actions execute only for the winning
token, at the appropriate input position. Use `self.text`, `self.type`, and
`self._channel`; ANTLR's Python target does not allow `$` attributes in lexers.

Grammar `@header {...}` and `@members {...}` blocks add module imports and class
members. In a combined grammar, unscoped blocks apply to both recognizers;
`@parser::header`, `@parser::members`, `@lexer::header`, and `@lexer::members`
select one recognizer. Imported grammar actions are preserved. Action bodies
become ordinary generated Python methods; no runtime `eval` or `exec` is used.
As with the original Python target, grammars containing actions are executable
Python source and must be trusted.

Parser action blocks share a real Python scope, including closure cells. A
function or lambda defined in `@init` observes later assignments to captured
locals. `return` exits the rule early while cleanup runs; it can return an
arbitrary Python value, just like an explicit return in ANTLR-generated Python.
Top-level `yield` inside a recognizer action is rejected because it would turn
the recognizer method into a generator instead of parsing. Nested helper
functions and visitors can use generators normally.

## Rule exceptions and nonlocal attributes

Parser rules can have Python exception clauses after the terminating semicolon:

```antlr
item returns [value: int]
    : number=INT {$value = int($number.text)};
catch [ValueError as problem] {
    self.errors.append(str(problem))
    $value = 0
}
finally {
    self.completed += 1
}
```

Catch declarations use Python syntax: `ValueError as problem`,
`(ValueError, TypeError) as problem`, or an empty declaration `catch []` for a
catch-all handler. They are tried in order. Supplying any custom catches
**replaces** that rule's default recognition-error handler; unmatched exceptions
propagate to callers. Use `catch [RecognitionException as problem]` and call
`self._errHandler.reportError(self, problem)` / `recover(self, problem)` when a
custom handler should preserve normal error reporting and recovery.

Successful parsing runs `@after`, then `finally`, then exit-listener callbacks.
A caught exception skips `@after` and still runs `finally`; an unhandled exception
runs `finally` while unwinding. Python locals from earlier action blocks remain
available in the handler/finally body. A handler may use bare `raise` or raise a
replacement exception. An exception from `finally` replaces a pending exception,
and parser context/precedence state is restored during unwinding. `@init` runs
before the rule's protected body, so its own catches/finally do not protect it.

Custom exception clauses are supported on non-left-recursive parser rules.
For a directly left-recursive expression rule, put the clauses on a wrapper
rule that invokes it. ANTLR 4.13.2 silently drops such clauses on the recursive
rule; this generator rejects them before producing output. Lexer exception
clauses remain unsupported; ordinary lexer action returns retain their native
helper-method meaning.

Use `$rule::attribute` to access a declared argument, return, or local attribute
on the nearest active invocation of a named rule:

```antlr
scope locals [total: int = 0]: '(' item* ')';
item: number=INT {$scope::total = $scope::total + $number.int};
```

The same reference works in predicates and rule-call arguments, such as
`{$scope::total < 10}?` and `child[$scope::total]`. Recursive calls select the
nearest matching context, including the current invocation when appropriate.
Unknown rules/attributes are rejected during generation; accessing a declared
scope that is not active raises `AttributeError`, matching the runtime's
`getInvokingContext` behavior. Imported rules keep these semantics after rule
indices are assigned in the composed grammar.

## Error recovery

Strict parsing remains the default: a syntax or lexical error raises
`SyntaxError`. To use ANTLR-style recovery, opt in on each recognizer:

```python
lexer = NumbersLexer(InputStream("12,,34"), recover=True)
parser = NumbersParser(CommonTokenStream(lexer), recover=True)
tree = parser.start()
print(parser.getNumberOfSyntaxErrors())  # 1
# The extra comma is retained as an error node in the partial parse tree.
```

Recovery uses the pinned Python runtime's `DefaultErrorStrategy`. It can delete
an unexpected token, synthesize a missing token, synchronize loops, or return
from a failed rule at a token that can follow it. Recovery reports diagnostics
to normal ANTLR error listeners (stderr by default) and returns a partial tree;
a returned tree alone does not establish valid input. Missing tokens have
`tokenIndex == -1`, and labels can hold these synthesized token objects.
Consumed unwanted tokens become error nodes, available through the standard
`visitErrorNode` callbacks. Inserted-node live callback behavior matches the
Python runtime. The default recognition handler sets `ctx.exception` and skips
`@after`; successfully repaired inline matches still run `@after`. Custom catch
clauses control their own reporting and context exception fields.

The lexer and parser opt in independently. Lexical recovery reports an
unrecognized character and skips it, following the native runtime. Lexer errors
are delivered to lexer listeners and are not included in the parser's syntax
error count. Use `removeErrorListeners()` and `addErrorListener(listener)` to
collect diagnostics. Calling `reset()` clears parser error counts and resets the
selected strategy.

You can also replace the strategy directly, including on a strict parser:

```python
from antlr4.error.ErrorStrategy import DefaultErrorStrategy, BailErrorStrategy

parser._errHandler = DefaultErrorStrategy()  # recover
# Or stop immediately with ParseCancellationException:
parser._errHandler = BailErrorStrategy()
```

Cancellation marks active contexts and unwinds rule/listener/precedence state.
Exceptions not handled by grammar catch clauses continue to propagate.
Regenerate recognizer modules with version 0.9 to receive the recovery-aware
lookahead and token-set handling. The reference cases cover the implemented
subset, not every malformed grammar/input combination supported by ANTLR.

## Options, names, and command-line compatibility

Python-target options include `language=Python3`, `tokenVocab`, `superClass`,
`contextSuperClass`, `TokenLabelType`, and `caseInsensitive`. Python ignores
`accessLevel` and `exportMacro`, as does the reference Python target. Custom
recognizer bases are combined with the ATN execution mixin; custom context bases
must implement the normal `ParserRuleContext` constructor/API. Put base classes
in importable modules beside the generated recognizers, or import/define them
in header blocks. `TokenLabelType` is an annotation option; token factories
continue to control actual token classes.

Rules, attributes, labels, and getters use the Python target's reserved-word
escaping, for example `class_`, `type_`, `int_`, and `reset_`. Raw grammar names
remain in rule/token metadata. Access modifiers and `throws` declarations are
accepted without adding Java-style visibility or checked exceptions to Python.
Semantic predicates support `<fail='custom message'>` and Python failure-message
expressions. Lexer commands accept symbolic and numeric arguments.

The CLI accepts multiple input grammars and orders token-vocabulary dependencies:

```sh
python -m antlr4_generator Sentence.g4 Words.g4 -Dlanguage=Python3 \
    -encoding utf-8 -visitor -package generated -o generated
python -m antlr4_generator --version
```

`-Dname=value` overrides a root grammar option. The API equivalents are
`generate(..., options={"caseInsensitive": True}, encoding="utf-8", package="generated")`.
`-package` creates a package marker in the chosen output directory while
preserving an existing `__init__.py`. `-Xexact-output-dir` is accepted because
output already goes directly to `-o`. All generation still works with no Java
or other tools on `PATH`. Java GUI/debugging and diagnostic-only CLI flags are
outside this Python module interface.

## Standalone lexer example

Save as `Quoted.g4`:

```antlr
lexer grammar Quoted;
tokens { STRING }
OPEN: '"' -> more, pushMode(QUOTED);
ID: LETTER+;
fragment LETTER: [\p{L}];
WS: [ \t\r\n]+ -> channel(HIDDEN);
mode QUOTED;
CLOSE: '"' -> type(STRING), popMode;
ESC: '\\' . -> more;
TEXT: ~["\\]+ -> more;
```

```sh
python -m antlr4_generator Quoted.g4 -o generated
```

This emits `Quoted.py` containing class `Quoted`, matching ANTLR's naming for
standalone lexers. Combined grammars still emit `NameLexer.py` and `NameParser.py`.
The `generate()` API returns a one-element tuple for a standalone lexer.

```python
from antlr4 import InputStream, CommonTokenStream
from generated.Quoted import Quoted

stream = CommonTokenStream(Quoted(InputStream('hello "world"')))
stream.fill()
print([(token.type, token.text, token.channel) for token in stream.tokens])
```

Hidden/custom-channel tokens are retained in the buffered stream; a parser
normally reads only the default channel. Declare custom channels with
`channels { COMMENTS }` before the rules. Apply commands to a whole rule, using
`('a' | 'b') -> skip` when alternatives need a common command. Fragments are
callable helpers, not token types. Modes require a standalone lexer grammar,
as they do in ANTLR. A separate parser can use the emitted token vocabulary as
shown below.

Unicode data is bundled, independent of the host Python's Unicode version.
There are 1,185 property sets and 2,558 aliases extracted from the pinned ANTLR
4.13.2 jar (ICU 72.1 / Unicode 15.0), including categories, scripts, blocks,
binary properties, and enumerated properties. Examples: `[\p{L}]`,
`[\p{Script=Greek}]`, `[\p{Block=Arrows}]`, `[\p{Emoji}]`, and
`[\P{XID_Continue}]`. Literals/ranges accept non-BMP code points such as
`'\u{1F600}'`. Unknown properties raise `GrammarError`.

`options {caseInsensitive=true;}` applies to a lexer or combined grammar;
a lexer rule can override it with `options {caseInsensitive=false;}`. Matching
uses simple upper/lower mappings, preserving original token text. The bundled
case mapping snapshot comes from the Java 11 reference environment; generation
and recognition never load Java. This repository includes the precomputed
data and its licenses; no Java-based regeneration tooling is included.

## Separate grammars, vocabularies, and imports

Save a lexer as `Words.g4`:

```antlr
lexer grammar Words;
ID: [a-z]+;
PLUS: '+';
WS: [ \t\r\n]+ -> skip;
```

Save a parser as `Sentence.g4`:

```antlr
parser grammar Sentence;
options { tokenVocab=Words; }
start: ID ('+' ID)* EOF;
```

Generate the lexer first, then the parser into the same directory:

```sh
python -m antlr4_generator Words.g4 -o generated
python -m antlr4_generator Sentence.g4 -o generated
```

This writes `Words.py`, `Words.tokens`, `Sentence.py`, and `Sentence.tokens`.
Use classes `Words` and `Sentence` with `InputStream` and `CommonTokenStream`.
Standalone parsers are named after the grammar, without an added `Parser`
suffix. Combined grammars emit both `Name.tokens` and `NameLexer.tokens`.
`generate()` still returns only Python module paths; vocabulary files are
sidecars and receive the same overwrite protection as modules.

Token IDs and literal aliases are read from `.tokens` files, including files
made by ANTLR 4.13.2. IDs are preserved even when sparse or shared by aliases;
new declared tokens are allocated after the largest existing ID. A separate
parser cannot invent a token for a new literal: declare it in the lexer and
regenerate the vocabulary first. Dependencies are never generated implicitly.

Add `import Common;` before the rules to inherit rules from `Common.g4`.
Parser grammars import parser grammars, lexer grammars import lexer grammars,
and combined grammars can import either kind or another combined grammar.
Root rules override imported rules, including references inside delegates.
Among delegates, the first rule encountered in depth-first import preorder
wins. Token/channel declarations are combined. Root options control the build;
delegate `tokenVocab` options are not applied independently.

Use repeatable `-lib` directories when dependencies live elsewhere:

```sh
python -m antlr4_generator Sentence.g4 -lib grammars -lib vocabularies -o generated
```

```python
generate("Sentence.g4", "generated", library_dirs=["grammars", "vocabularies"])
```

Imports are resolved beside the importing file, then in the library directories,
then beside the root grammar. Vocabularies are searched in library directories,
the output directory, then beside the root grammar. Missing dependencies,
cycles, incompatible grammar kinds, and invalid vocabulary entries raise
`GrammarError` before output files are written. Import aliases (`A=Common`) are
accepted. ANTLR 4 does not interpret `Common.rule` as a qualified delegate call:
it parses that text as a token reference, wildcard, and rule reference. Imported lexer modes
require a standalone lexer root.

## Expression example

```antlr
grammar Arithmetic;
start: expr EOF;
expr: '-' expr
    | <assoc=right> expr '^' expr
    | expr ('*' | '/') expr
    | expr ('+' | '-') expr
    | '(' expr ')'
    | INT
    ;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
```

Generate and use `ArithmeticLexer` and `ArithmeticParser` as in the example
above, calling `parser.start()`. `2+3*4` groups as `2+(3*4)`, `8-3-1` as
`(8-3)-1`, and `2^3^4` as `2^(3^4)`. Prefix `-` binds more tightly than `^`
in this example because its alternative appears first. Moving that alternative
changes its binding strength, matching ANTLR's alternative-order convention.

Keep the `start: expr EOF;` rule even when calling `parser.expr()` directly.
ANTLR 4.13.2 can report an end-of-input prediction error for a left-recursive
rule without an entry-rule continuation; this prototype also rejects that
case with `SyntaxError`. Recursive methods accept the usual optional `_p=0`
precedence argument. Missing primary alternatives, nullable recursion suffixes,
and unsupported recursion cycles produce `GrammarError` before files are written.

## Architecture and validation

`composition.py` resolves delegate files, integrates rules, and loads/writes
token vocabularies. `grammar.py` reads the grammar, resolves tokens, and rewrites direct left
recursion into a primary expression plus a precedence-guarded loop. Recursive
operands receive binding arguments based on alternative order and associativity.
It checks remaining recursion cycles and nullable loops. `atn.py` constructs
lexer and parser ATNs, marks precedence rules, and serializes them
using ANTLR's version-4 integer format, including rule returns, decisions, loops,
character sets, EOF, lexer modes, fragments, lexer commands, and embedded
action/predicate transitions.
Every constructed ATN is verified
by the existing Python runtime's deserializer before generation succeeds.

Generated modules contain `serializedATN()` and a deserialized `atn`, as standard
ANTLR-generated Python modules do. `runtime.py` uses `LexerATNSimulator` for
lexing and walks parser ATNs. Disjoint, predicate-free decisions use ANTLR-style
LL(1) lookahead; overlapping/predicate decisions use
`ParserATNSimulator.adaptivePredict`. Native rule invocation contexts allow prediction through rule returns;
parser rule invocation itself is iterative. DFA caches are reused within each
recognizer instance. Native recursion contexts build left/right-associated
expression trees and native precedence stacks control nested operands. Errors
restore parser context and precedence state. There is no regex-based lexer or
FIRST-set-only execution.

`tree_api.py` derives accessor cardinalities from the original grammar before
left-recursion rewriting, then emits nested context classes and tree helpers.
The generated modules still depend on this package's ATN execution helpers;
they do not reproduce the reference generator's Python method bodies.
`action_sessions.py` emits suspended dispatchers that preserve real Python rule
locals and closure cells across ATN positions; it never evaluates source text at
runtime. These helpers also implement early-return and exception cleanup.
The closed milestone list and remaining compatibility boundaries are recorded
in [COMPATIBILITY.md](COMPATIBILITY.md).

Run tests from this directory:

```sh
python -m unittest discover -s tests -v
```

Tests include saved ANTLR 4.13.2 reference fixtures for seven combined grammars
and two standalone lexers: token
types/text/positions/channels, parse trees, and invalid-input rejection. They
also check serializer round trips against both our ATNs and reference ATNs.
Expression cases include binary, prefix, postfix, parentheses, right-associative
power and conditional operators, and primary alternatives interleaved with
operator alternatives.
Lexer cases compare mode stacks and final modes as well as tokens, including
fragments, channel commands, Unicode categories, nongreedy matching, and
unterminated strings under the reference lexer's EOF behavior.
Three additional composition scenarios compare token vocabularies and behavior
for separate lexer/parser generation, parser-rule overrides, imported lexer
fragments, and transitive import precedence. The parser tests also consume
saved vocabularies produced by the original Java generator.
Seven additional reference cases compare context classes and accessor
signatures/results, visitor dispatch order, source intervals, tree-walk
callbacks, and callbacks registered during parsing.
Six further reference cases compare labeled contexts, label fields, rule
attributes, and the timing of visitor/listener callbacks.
Fourteen action/predicate reference cases compare computed values, action side
effects, ordinary Python locals, predicate choices, lexer action positions, and
listener timing.
Forty-five recovery reference cases compare diagnostics, syntax-error counts,
partial trees, error nodes, synthesized label tokens, rule exceptions, source
intervals, and live/tree-walk callbacks, including lexical recovery.
Sixteen exception/nonlocal reference cases compare handler selection,
propagation, ordinary locals, lifecycle/listener order, nearest recursive scopes,
nonlocal predicates, and nonlocal rule-call arguments.
Thirty-six completion/corpus cases compare wildcard and negated tokens,
nongreedy parser decisions, case-insensitive rules, recursive lexers, Unicode
properties, Python call arguments, closures/returns, keyword escaping, and three
larger repository grammars.
The reference data is checked in, so normal tests require **no Java**.

The checked-in reference fixtures cover supported workloads, rather than
certifying compatibility with every possible ANTLR grammar.

The code is distributed under the repository's BSD-3-Clause license. Bundled
Unicode tables also carry the Unicode data license. Both notices are included
in package distributions as `LICENSE.txt` and `UNICODE-LICENSE.txt`.
