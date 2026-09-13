;; Rust extraction query.
;;
;; Rust has no classes: `struct_item` maps to @def.class, `trait_item` to
;; @def.interface, `enum_item` to @def.enum and `type_item` to @def.type.
;; Free functions are those directly under the file; functions inside an
;; `impl_item` body are methods.

;; --- definitions -----------------------------------------------------------

(struct_item
  name: (type_identifier) @name.class) @def.class

(enum_item
  name: (type_identifier) @name.enum) @def.enum

(trait_item
  name: (type_identifier) @name.interface) @def.interface

(type_item
  name: (type_identifier) @name.type) @def.type

(mod_item
  name: (identifier) @name.module) @def.module

(impl_item
  body: (declaration_list
    (function_item
      name: (identifier) @name.method) @def.method))

(source_file
  (function_item
    name: (identifier) @name.function) @def.function)

(field_declaration
  name: (field_identifier) @name.field) @def.field

;; --- inheritance (trait implementation) ------------------------------------

(impl_item
  trait: (type_identifier) @inherit)

;; --- imports ---------------------------------------------------------------

(use_declaration
  argument: (scoped_identifier) @import.module)

(use_declaration
  argument: (identifier) @import.module)

(use_declaration
  argument: (use_as_clause
    path: (scoped_identifier) @import.module
    alias: (identifier) @import.alias))

;; --- calls -----------------------------------------------------------------

(call_expression
  function: (identifier) @call.fn)

(call_expression
  function: (field_expression
    value: (_) @call.recv
    field: (field_identifier) @call.attr))

;; --- documentation ---------------------------------------------------------

(line_comment) @doc

(block_comment) @doc
