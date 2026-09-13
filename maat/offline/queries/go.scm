;; Go extraction query.

;; --- definitions -----------------------------------------------------------

(function_declaration
  name: (identifier) @name.function) @def.function

(method_declaration
  name: (field_identifier) @name.method) @def.method

(type_declaration
  (type_spec
    name: (type_identifier) @name.class
    type: (struct_type)) @def.class)

(type_declaration
  (type_spec
    name: (type_identifier) @name.interface
    type: (interface_type)) @def.interface)

(type_declaration
  (type_spec
    name: (type_identifier) @name.type
    type: (type_identifier)) @def.type)

(field_declaration
  name: (field_identifier) @name.field) @def.field

(package_clause
  (package_identifier) @name.module) @def.module

;; --- imports ---------------------------------------------------------------

(import_spec
  path: (interpreted_string_literal) @import.module)

(import_spec
  name: (package_identifier) @import.alias
  path: (interpreted_string_literal) @import.module)

;; --- calls -----------------------------------------------------------------

(call_expression
  function: (identifier) @call.fn)

(call_expression
  function: (selector_expression
    operand: (_) @call.recv
    field: (field_identifier) @call.attr))

;; --- documentation ---------------------------------------------------------

(comment) @doc
