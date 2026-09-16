;; Scala extraction query.
;;
;; Scala's `def` is always a method (there are no free functions in normal
;; source), so both `function_definition` (concrete) and `function_declaration`
;; (abstract, e.g. in a trait) map to @def.method.

;; --- definitions -----------------------------------------------------------

(class_definition
  name: (identifier) @name.class) @def.class

(object_definition
  name: (identifier) @name.class) @def.class

(trait_definition
  name: (identifier) @name.interface) @def.interface

(type_definition
  name: (identifier) @name.type) @def.type

(function_definition
  name: (identifier) @name.method) @def.method

(function_declaration
  name: (identifier) @name.method) @def.method

(package_clause
  name: (package_identifier) @name.module) @def.module

;; --- inheritance -----------------------------------------------------------

(class_definition
  (extends_clause type: (type_identifier) @inherit))

(trait_definition
  (extends_clause type: (type_identifier) @inherit))

(object_definition
  (extends_clause type: (type_identifier) @inherit))

;; --- imports ---------------------------------------------------------------

(import_declaration
  (identifier) @import.module)

;; --- calls -----------------------------------------------------------------

(call_expression
  function: (identifier) @call.fn)

(call_expression
  function: (field_expression
    value: (_) @call.recv
    field: (identifier) @call.attr))

;; --- documentation ---------------------------------------------------------

(comment) @doc
