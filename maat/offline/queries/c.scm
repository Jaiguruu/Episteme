;; C extraction query.
;;
;; C has no classes or methods. `struct_specifier` / `union_specifier` map to
;; @def.class, `enum_specifier` to @def.enum and a `typedef` to @def.type.
;; Note the function name is nested: the `function_definition` carries a
;; `function_declarator`, whose `declarator` is the identifier -- hence the
;; declaration node and the name node are captured together per pattern.

;; --- definitions -----------------------------------------------------------

(struct_specifier
  name: (type_identifier) @name.class) @def.class

(union_specifier
  name: (type_identifier) @name.class) @def.class

(enum_specifier
  name: (type_identifier) @name.enum) @def.enum

(type_definition
  declarator: (type_identifier) @name.type) @def.type

(function_definition
  declarator: (function_declarator
    declarator: (identifier) @name.function)) @def.function

(field_declaration
  declarator: (field_identifier) @name.field) @def.field

;; --- imports ---------------------------------------------------------------

(preproc_include
  path: (string_literal) @import.module)

(preproc_include
  path: (system_lib_string) @import.module)

;; --- calls -----------------------------------------------------------------

(call_expression
  function: (identifier) @call.fn)

(call_expression
  function: (field_expression
    argument: (_) @call.recv
    field: (field_identifier) @call.attr))

;; --- documentation ---------------------------------------------------------

(comment) @doc
