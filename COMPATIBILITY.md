# Python generator milestone audit

Version **0.11.0a1** completes the planned Python-recognizer feature milestones.
It installs, generates recognizers, and runs them with Python and the pinned
`antlr4-python3-runtime==4.13.2`. No Java tooling is included in this standalone repository.

This is an experimental implementation. Completion of the feature roadmap does
not establish universal, byte-for-byte equivalence to the original tool.

| Milestone | Status and evidence |
| --- | --- |
| Grammar frontend and lexer/parser ATNs | Implemented; serialized ATNs round-trip through the native runtime. |
| Adaptive prediction and direct left recursion | Implemented; binary/prefix/postfix/conditional and right-associative reference cases. |
| Lexer modes, commands, Unicode and recursion | Implemented; modes, fragments, recursive nesting, numeric commands, 1,185 Unicode properties and 2,558 aliases. |
| Parser wildcard, negation and nongreedy constructs | Implemented; native reference comparisons, including invalid input and EOF. |
| Separate grammars, vocabularies, imports and aliases | Implemented; sparse IDs, overrides, transitive precedence, library lookup and CLI dependency ordering. |
| Contexts, accessors, visitors, listeners and labels | Implemented; typed/labeled contexts, scalar/list fields and live/tree-walk callback comparisons. |
| Rule attributes, actions and predicates | Implemented; Python expressions/calls, persistent locals and closure cells, early returns and nonlocal attributes. |
| Recovery and rule exception clauses | Implemented; insertion/deletion/resynchronization, bail, catch/finally and exception propagation. |
| Python options and target API names | Implemented; custom bases, case-insensitive rules, failure messages, modifiers and reserved-word escaping. |
| Packaging and representative grammar validation | Wheel/sdist tests run with Java absent from PATH; expression, XPath and adapted Java grammar reference cases are included. |

## Verified interface

The API is `antlr4_generator.generate(...)`; the CLI is `antlr4-python` or
`python -m antlr4_generator`. Recognizer modules expose serialized ATNs, token
and rule metadata/constants, typed contexts, rule entry methods and native
ANTLR token streams/listeners/visitors. Generated modules additionally require
this package's ATN execution helpers.

Source tests require no Java. The checked-in oracle data was produced by the
SHA-256-pinned official ANTLR 4.13.2 complete jar. The completion suite compares
tokens/positions/channels, trees, semantic results and diagnostics. Earlier
suites additionally compare fields, callback ordering, recovery nodes and
context exceptions. Passing these cases establishes those workloads; it is
not exhaustive conformance certification for every possible grammar.

## Deliberate differences and boundaries

- Only Python recognizers are emitted. Java, JavaScript and other output
  targets, the Java GUI and diagnostic-only tool flags are outside scope.
- Strict `SyntaxError` behavior remains the default for compatibility with
  earlier releases of this package. Pass `recover=True` to each recognizer, or
  select a native error strategy, for ANTLR-style recovery.
- Generated Python source and ATN state numbering differ from the Java tool's
  output. Runtime behavior and the supported API are the compatibility target.
- Top-level `yield` in a recognizer action is rejected. It would make the
  generated entry method return an iterator instead of parsing. Generators in
  helper functions and visitors are supported.
- Optional rule arguments accept literal defaults as a package extension;
  return/local initializers accept Python expressions. Contexts copy mutable
  literal defaults. Arbitrary Python source in grammars must be trusted.
- Names that still collide with runtime structure after Python escaping are
  rejected. Unknown/unsupported grammar options produce errors instead of the
  reference tool's sometimes nonfatal warnings.
- Unicode property data comes from ANTLR 4.13.2's ICU 72.1 tables. Simple case
  mappings are pinned to the Java 11 reference snapshot, avoiding host-Python
  Unicode drift. A reference tool running on a newer JDK can have different
  mappings for newly introduced cased characters.
- EOF repetition with `*`/`+` is guarded against nonprogress; optional EOF is
  supported. Nullable repetition and unsupported leading recursion are rejected.

## Restrictions inherited from, or guarded against, in the reference tool

These are not deferred implementation milestones:

- ANTLR 4 rejects indirect/unsupported leading recursion. Its tool also reports
  error 169 for argument-bearing left-recursive rules outside the supported
  transformation patterns. Use ordinary argument-bearing wrapper rules.
- ANTLR 4.13.2 silently discards custom catch/finally clauses attached directly
  to left-recursive rules. This package rejects those clauses and requires a
  nonrecursive wrapper, where handlers and cleanup are fully supported.
- ANTLR 4 import aliases do not create callable namespaces. `Base.rule` is
  parsed by the reference tool as a token, wildcard and rule reference, not a
  qualified delegate invocation. Imported rules are called by rule name.
- Some reference Python templates generate invalid source for reserved-word
  token properties and certain wildcard list labels. This implementation
  escapes names consistently and retains functioning list labels. The oracle
  corpus avoids those broken reference-template forms, with direct regression
  tests for this implementation's behavior.

## Corpus provenance

`CorpusExpr.g4` and `CorpusXPath.g4` derive from this repository's Python runtime
test grammar and XPath lexer; names are changed to isolate test imports.
`CorpusJava.g4` retains the original JavaLR grammar's copyright/license notice.
Its Java-specific identifier predicates are replaced with Unicode category
sets, allowing the same grammar to generate valid Python with both tools.
Reference samples include classes, methods, precedence expressions, loops,
XPath paths and function definitions.

## Reproducing validation

From the repository root, after installing the package:

```sh
python -m unittest discover -s tests -v
```

Reference snapshots and Unicode tables retain their upstream provenance.
Java-based oracle regeneration tools are deliberately excluded.
