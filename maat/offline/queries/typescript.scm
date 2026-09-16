;; TypeScript extraction query.
;;
;; Note: in this grammar a class/interface *name* is a `type_identifier`, not a
;; plain `identifier` (unlike JavaScript), so those patterns differ from
;; javascript.scm. See README.md.

;; --- definitions -----------------------------------------------------------

(class_declaration
  name: (type_identifier) @name.class) @def.class

(abstract_class_declaration
  name: (type_identifier) @name.class) @def.class

(interface_declaration
  name: (type_identifier) @name.interface) @def.interface

(enum_declaration
  name: (identifier) @name.enum) @def.enum

(type_alias_declaration
  name: (type_identifier) @name.type) @def.type

(function_declaration
  name: (identifier) @name.function) @def.function

(method_definition
  name: (property_identifier) @name.method) @def.method

(method_signature
  name: (property_identifier) @name.method) @def.method

(public_field_definition
  name: (property_identifier) @name.field) @def.field

(property_signature
  name: (property_identifier) @name.field) @def.field

;; --- inheritance -----------------------------------------------------------

(class_declaration
  (class_heritage (extends_clause value: (_) @inherit)))

(class_declaration
  (class_heritage (implements_clause (type_identifier) @inherit)))

(interface_declaration
  (extends_type_clause (type_identifier) @inherit))

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
