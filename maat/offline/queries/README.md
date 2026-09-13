# Extraction queries

One tree-sitter query per language: `<language>.scm`, where `<language>` is the
grammar key in `maat/offline/languages.py` (e.g. `python.scm`, `cpp.scm`).
`extractable_languages()` discovers these files from disk, so a language becomes
extractable the moment its `.scm` lands here and stops being extractable when it
is removed. Nothing else has to change.

The queries only *capture* nodes. Turning captures into `Symbol` / `Relationship`
objects is the consumer's job.

## Capture vocabulary

| Capture | Meaning |
| --- | --- |
| `@def.class` | class / struct declaration node |
| `@def.interface` | interface / protocol / trait declaration node |
| `@def.enum` | enum declaration node |
| `@def.function` | function declaration node |
| `@def.method` | method declaration node |
| `@def.constructor` | constructor declaration node |
| `@def.field` | field / property declaration node |
| `@def.type` | type alias / typedef node |
| `@def.module` | namespace / package / module declaration node |
| `@name.class` | the identifier of a `@def.class` |
| `@name.interface` | the identifier of a `@def.interface` |
| `@name.enum` | the identifier of a `@def.enum` |
| `@name.function` | the identifier of a `@def.function` |
| `@name.method` | the identifier of a `@def.method` |
| `@name.constructor` | the identifier of a `@def.constructor` |
| `@name.field` | the identifier of a `@def.field` |
| `@name.type` | the identifier of a `@def.type` |
| `@name.module` | the identifier of a `@def.module` |
| `@inherit` | a base type / superclass / implemented trait name |
| `@import.module` | module path or source specifier of an import |
| `@import.name` | an imported symbol name |
| `@import.alias` | an import alias |
| `@call.fn` | callee name of a direct call |
| `@call.recv` | receiver expression of a member / method call |
| `@call.attr` | member / method name of a member call |
| `@doc` | documentation comment or docstring |

## The two-capture-per-pattern convention

Every definition pattern captures **both** the declaration node and its name
node, in the same pattern:

```scheme
(class_definition name: (identifier) @name.class) @def.class
(function_definition name: (identifier) @name.function) @def.function
```

`@def.*` wraps the whole declaration; `@name.*` wraps just the identifier. The
consumer uses `QueryCursor.matches()` and pairs the two captures *within a
single match*.

This matters because the name node's parent is frequently **not** the
declaration node. In C, for example:

```
(function_definition
  declarator: (function_declarator
    declarator: (identifier)))          ; <- name lives two levels down
```

Capturing only the identifier would give the consumer a node whose parent is a
`function_declarator`, not a `function_definition`, and there would be no
declaration node to attach a span or signature to. Capturing both in one pattern
makes the grouping explicit and language-independent.

Constructors are the one exception: some grammars model them without an
identifier child (`init_declaration` in Swift, `primary_constructor` in Kotlin),
so those matches legitimately carry only `@def.constructor`.

## Per-language quirks

* **javascript vs typescript / tsx** — a JS class name is an `identifier`; a TS
  class or interface name is a `type_identifier`. The two files differ for that
  reason.
* **java** — no free functions, so `method_declaration` is always `@def.method`.
  Member calls are separated from direct calls with the `.` anchor
  (`(method_invocation . name: …)`) so a call is never captured twice.
* **c** — no classes or methods; `struct_specifier` / `union_specifier` map to
  `@def.class`. The function name is nested inside a `function_declarator`.
* **cpp** — an inline method's name is a `field_identifier` but an inline
  constructor's name is a plain `identifier`; the constructor pattern is
  therefore anchored to a `field_declaration_list` so it cannot swallow free
  functions. Free functions are anchored to the `translation_unit`.
* **csharp** — `this.M()` has no `expression` child (the `this` keyword is
  anonymous), so it needs a leading-name pattern; `obj.M()` uses the receiver
  pattern. The `.` anchor keeps them from overlapping.
* **go** — `type_spec` with a `struct_type` / `interface_type` maps to
  `@def.class` / `@def.interface`; a plain alias (`type A B`) maps to `@def.type`
  so structs and interfaces are not double-reported.
* **rust** — free functions are those directly under `source_file`; functions in
  an `impl_item` body are `@def.method`. `impl Trait for Type` yields `@inherit`.
* **ruby** — `require` / `require_relative` are ordinary calls, captured as
  `@import.module` via an `#eq?` predicate. Ruby's `def` is a `method` node at
  any nesting, so all definitions are `@def.method`.
* **php** — `__construct` is an ordinary `method_declaration`, so it is captured
  as `@def.method`, not `@def.constructor`.
* **kotlin** — the grammar exposes **no field names**, so every pattern is
  positional. `class` and `interface` share `class_declaration` and are told
  apart by the anonymous keyword token. Constructors have no name child.
* **swift** — `class`, `struct`, `enum` and `extension` all parse as
  `class_declaration`; only the leading keyword token distinguishes them.
  `extension` additionally wraps its name in a `user_type`.
* **scala** — `def` is always a method (`function_definition` concrete,
  `function_declaration` abstract). `object` maps to `@def.class`.
* **lua** — no classes; `function T.m()` and `function T:m()` map to
  `@def.method`, plain `function f()` to `@def.function`. `require("mod")` is a
  call captured as `@import.module` by predicate.
* **bash** — `source` and `.` are commands captured as `@import.module` by
  predicate. Every command word is treated as a call target.
* **dart** — `mixin` is a `mixin_declaration` here (not `mixin_definition`) and
  its `on` type is a bare positional child. Calls are `expression_statement`s
  with a trailing `selector`/`argument_part`; there is no
  `function_expression_invocation` node.

## Known partial coverage

Honest list of what these queries do **not** capture:

* **Nested definitions.** Where a pattern is anchored to a top-level container
  (Python module functions, Rust `source_file` functions, C++ free functions),
  definitions nested inside another block/module are not captured. This is
  deliberate: it is how methods are kept distinct from free functions without a
  negated-parent predicate, which tree-sitter does not provide.
* **Python** — `__init__` is reported as a method, not a constructor. Functions
  nested inside functions are not captured.
* **Ruby** — a `require` whose argument is not a string literal is not captured.
* **Bash** — a `source` whose argument is a quoted or expanded string is not
  captured; variable assignments are approximated as `@def.field` (the shell has
  no real fields).
* **Lua** — no `@def.class` / `@def.field` (the language has neither); a
  `require` with a non-literal argument is not captured.
* **tsx** — the sample used for verification contains no call expression at all,
  so the `@call.*` patterns are exercised only by a supplementary snippet.
  JSX elements are intentionally not treated as calls.
* **Doc comments** — only the Python and Bash samples contain a documentation
  node, so `@doc` is only proven there. Every file has a `@doc` pattern against
  the comment node(s) its grammar defines (`comment`, `line_comment`,
  `block_comment`, `multiline_comment`, `documentation_comment`).

## Verifying

`tools/verify_queries.py` parses the representative sample per language from
`tools/dump_trees.py`, compiles each `.scm`, runs `QueryCursor.matches()`, and
asserts that a definition, a call and an import capture all fire (and that the
two-capture convention holds). It exits non-zero if any language fails.

```bash
python tools/verify_queries.py
```
