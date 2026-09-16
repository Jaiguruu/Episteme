;; Swift extraction query.
;;
;; The grammar uses a single `class_declaration` node for `class`, `struct`,
;; `enum` and `extension`; only the leading keyword token distinguishes them, so
;; those definitions are separated with anonymous-token guards. `extension` also
;; differs in that its name is wrapped in a `user_type`.

;; --- definitions -----------------------------------------------------------

(class_declaration
  "class" name: (type_identifier) @name.class) @def.class

(class_declaration
  "struct" name: (type_identifier) @name.class) @def.class

(class_declaration
  "enum" name: (type_identifier) @name.enum) @def.enum

(class_declaration
  "extension" name: (user_type
    (type_identifier) @name.class)) @def.class

(protocol_declaration
  name: (type_identifier) @name.interface) @def.interface

(source_file
  (function_declaration
    name: (simple_identifier) @name.function) @def.function)

(class_body
  (function_declaration
    name: (simple_identifier) @name.method) @def.method)

(protocol_body
  (protocol_function_declaration
    name: (simple_identifier) @name.method) @def.method)

(init_declaration) @def.constructor

(property_declaration
  name: (pattern
    bound_identifier: (simple_identifier) @name.field)) @def.field

;; --- inheritance -----------------------------------------------------------

(class_declaration
  (inheritance_specifier
    inherits_from: (user_type (type_identifier) @inherit)))

;; --- imports ---------------------------------------------------------------

(import_declaration
  (identifier (simple_identifier) @import.module))

;; --- calls -----------------------------------------------------------------

(call_expression
  (simple_identifier) @call.fn)

(call_expression
  (navigation_expression
    target: (_) @call.recv
    suffix: (navigation_suffix
      suffix: (simple_identifier) @call.attr)))

;; --- documentation ---------------------------------------------------------

(comment) @doc

(multiline_comment) @doc
