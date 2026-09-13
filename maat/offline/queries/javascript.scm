;; JavaScript extraction query.
;;
;; Convention: @def.* wraps the declaration node, @name.* wraps its identifier,
;; both inside one pattern so they group into a single match. See README.md.

;; --- definitions -----------------------------------------------------------

(class_declaration
  name: (identifier) @name.class) @def.class

(function_declaration
  name: (identifier) @name.function) @def.function

(method_definition
  name: (property_identifier) @name.method) @def.method

(field_definition
  property: (property_identifier) @name.field) @def.field

;; --- inheritance -----------------------------------------------------------

(class_declaration
  (class_heritage (_) @inherit))

;; --- imports ---------------------------------------------------------------

(import_statement
  source: (string) @import.module)

(import_statement
  (import_clause
    (named_imports
      (import_specifier name: (identifier) @import.name))))

(import_statement
  (import_clause
    (named_imports
      (import_specifier
        name: (identifier) @import.name
        alias: (identifier) @import.alias))))

(import_statement
  (import_clause (identifier) @import.name))

(import_statement
  (import_clause (namespace_import (identifier) @import.name)))

;; --- calls -----------------------------------------------------------------

(call_expression
  function: (identifier) @call.fn)

(call_expression
  function: (member_expression
    object: (_) @call.recv
    property: (property_identifier) @call.attr))

;; --- documentation ---------------------------------------------------------

(comment) @doc
