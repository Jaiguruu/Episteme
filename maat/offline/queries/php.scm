;; PHP extraction query.
;;
;; `__construct` is an ordinary `method_declaration` in this grammar, so it is
;; captured as @def.method rather than @def.constructor (see README.md).

;; --- definitions -----------------------------------------------------------

(class_declaration
  name: (name) @name.class) @def.class

(interface_declaration
  name: (name) @name.interface) @def.interface

(trait_declaration
  name: (name) @name.interface) @def.interface

(enum_declaration
  name: (name) @name.enum) @def.enum

(method_declaration
  name: (name) @name.method) @def.method

(function_definition
  name: (name) @name.function) @def.function

(property_declaration
  (property_element
    name: (variable_name (name) @name.field))) @def.field

(namespace_definition
  name: (namespace_name) @name.module) @def.module

;; --- inheritance -----------------------------------------------------------

(class_declaration
  (base_clause (name) @inherit))

(class_declaration
  (class_interface_clause (name) @inherit))

(interface_declaration
  (base_clause (name) @inherit))

;; --- imports ---------------------------------------------------------------

(namespace_use_clause
  (qualified_name) @import.module)

(namespace_use_clause
  (qualified_name) @import.module
  alias: (name) @import.alias)

;; --- calls -----------------------------------------------------------------

(function_call_expression
  function: (name) @call.fn)

(member_call_expression
  object: (_) @call.recv
  name: (name) @call.attr)

;; --- documentation ---------------------------------------------------------

(comment) @doc
