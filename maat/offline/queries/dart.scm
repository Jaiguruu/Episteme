;; Dart extraction query.
;;
;; A top-level function is a `function_signature` directly under `program`; a
;; method is a `function_signature` nested in a `method_signature` (concrete) or
;; directly in a class-body `declaration` (abstract). Anchoring each case keeps
;; the same node from being reported twice.
;;
;; Quirks: `mixin` is a `mixin_declaration` here (not `mixin_definition`) and
;; its `on` type is a bare positional child. A call is an `expression_statement`
;; whose trailing `selector` holds an `argument_part`; there is no
;; `function_expression_invocation` node in this grammar.

;; --- definitions -----------------------------------------------------------

(class_definition
  name: (identifier) @name.class) @def.class

(mixin_declaration
  (mixin) (identifier) @name.class) @def.class

(enum_declaration
  name: (identifier) @name.enum) @def.enum

(program
  (function_signature
    name: (identifier) @name.function) @def.function)

(method_signature
  (function_signature
    name: (identifier) @name.method) @def.method)

(class_body
  (declaration
    (function_signature
      name: (identifier) @name.method) @def.method))

(constructor_signature
  name: (identifier) @name.constructor) @def.constructor

(initialized_identifier
  (identifier) @name.field) @def.field

;; --- inheritance -----------------------------------------------------------

(class_definition
  (superclass (type_identifier) @inherit))

(class_definition
  (interfaces (type_identifier) @inherit))

(mixin_declaration
  (interfaces (type_identifier) @inherit))

(mixin_declaration
  (identifier) (type_identifier) @inherit)

;; --- imports ---------------------------------------------------------------

(import_or_export
  (library_import
    (import_specification
      (configurable_uri
        (uri (string_literal) @import.module)))))

;; --- calls -----------------------------------------------------------------
;;
;; `foo(1)` is an identifier immediately followed by an argument selector; a
;; member call has an intervening property selector and is matched separately,
;; so neither form is captured twice.

(expression_statement
  (identifier) @call.fn
  . (selector (argument_part)))

(expression_statement
  (_) @call.recv
  (selector
    (unconditional_assignable_selector (identifier) @call.attr))
  (selector (argument_part)))

;; --- documentation ---------------------------------------------------------

(comment) @doc

(documentation_comment) @doc
