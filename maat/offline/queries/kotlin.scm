;; Kotlin extraction query.
;;
;; This grammar exposes NO field names, so every pattern is positional. That
;; makes the child order load-bearing: e.g. a `class_declaration` is
;; `"class"|"interface" type_identifier ...`, hence the anonymous-token guard
;; that separates @def.class from @def.interface.

;; --- definitions -----------------------------------------------------------

(class_declaration
  "class" (type_identifier) @name.class) @def.class

(class_declaration
  "interface" (type_identifier) @name.interface) @def.interface

(object_declaration
  (type_identifier) @name.class) @def.class

(source_file
  (function_declaration
    (simple_identifier) @name.function) @def.function)

(class_body
  (function_declaration
    (simple_identifier) @name.method) @def.method)

(primary_constructor) @def.constructor

(secondary_constructor) @def.constructor

(class_parameter
  (simple_identifier) @name.field) @def.field

(property_declaration
  (variable_declaration
    (simple_identifier) @name.field)) @def.field

(package_header
  (identifier (simple_identifier) @name.module)) @def.module

;; --- inheritance -----------------------------------------------------------

(delegation_specifier
  (user_type (type_identifier) @inherit))

(delegation_specifier
  (constructor_invocation
    (user_type (type_identifier) @inherit)))

;; --- imports ---------------------------------------------------------------

(import_header
  (identifier (simple_identifier) @import.module))

;; --- calls -----------------------------------------------------------------

(call_expression
  (simple_identifier) @call.fn)

(call_expression
  (navigation_expression
    (_) @call.recv
    (navigation_suffix (simple_identifier) @call.attr)))

;; --- documentation ---------------------------------------------------------

(line_comment) @doc

(multiline_comment) @doc
