;; C++ extraction query.
;;
;; Inside a class body an inline method's name is a `field_identifier` while an
;; inline constructor's name is a plain `identifier`; the constructor pattern is
;; therefore anchored to a `field_declaration_list` so it cannot swallow free
;; functions. Free functions are anchored to the `translation_unit`.

;; --- definitions -----------------------------------------------------------

(class_specifier
  name: (type_identifier) @name.class) @def.class

(struct_specifier
  name: (type_identifier) @name.class) @def.class

(union_specifier
  name: (type_identifier) @name.class) @def.class

(enum_specifier
  name: (type_identifier) @name.enum) @def.enum

(namespace_definition
  name: (namespace_identifier) @name.module) @def.module

(type_definition
  declarator: (type_identifier) @name.type) @def.type

(alias_declaration
  name: (type_identifier) @name.type) @def.type

(function_definition
  declarator: (function_declarator
    declarator: (field_identifier) @name.method)) @def.method

(function_definition
  declarator: (function_declarator
    declarator: (qualified_identifier
      name: (identifier) @name.method))) @def.method

(field_declaration_list
  (function_definition
    declarator: (function_declarator
      declarator: (identifier) @name.constructor)) @def.constructor)

(translation_unit
  (function_definition
    declarator: (function_declarator
      declarator: (identifier) @name.function)) @def.function)

(field_declaration
  declarator: (field_identifier) @name.field) @def.field

;; --- inheritance -----------------------------------------------------------

(class_specifier
  (base_class_clause (type_identifier) @inherit))

(struct_specifier
  (base_class_clause (type_identifier) @inherit))

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
