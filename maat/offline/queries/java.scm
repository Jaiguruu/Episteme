;; Java extraction query.
;;
;; Java has no free functions: `method_declaration` only ever appears inside a
;; type body, so it maps cleanly to @def.method. Constructors are a distinct
;; node type, so they map to @def.constructor without overlapping.

;; --- definitions -----------------------------------------------------------

(class_declaration
  name: (identifier) @name.class) @def.class

(interface_declaration
  name: (identifier) @name.interface) @def.interface

(annotation_type_declaration
  name: (identifier) @name.interface) @def.interface

(enum_declaration
  name: (identifier) @name.enum) @def.enum

(record_declaration
  name: (identifier) @name.class) @def.class

(method_declaration
  name: (identifier) @name.method) @def.method

(constructor_declaration
  name: (identifier) @name.constructor) @def.constructor

(field_declaration
  declarator: (variable_declarator
    name: (identifier) @name.field)) @def.field

(package_declaration
  (scoped_identifier) @name.module) @def.module

;; --- inheritance -----------------------------------------------------------

(class_declaration
  superclass: (superclass (type_identifier) @inherit))

(class_declaration
  interfaces: (super_interfaces
    (type_list (type_identifier) @inherit)))

(interface_declaration
  (extends_interfaces
    (type_list (type_identifier) @inherit)))

;; --- imports ---------------------------------------------------------------

(import_declaration
  (scoped_identifier) @import.module)

;; --- calls -----------------------------------------------------------------
;;
;; `.` before `name:` restricts the direct-call pattern to invocations whose
;; first child is the method name (i.e. no explicit receiver), so a member call
;; is captured once, by the @call.attr pattern, instead of twice.

(method_invocation
  . name: (identifier) @call.fn)

(method_invocation
  object: (_) @call.recv
  name: (identifier) @call.attr)

;; --- documentation ---------------------------------------------------------

(line_comment) @doc

(block_comment) @doc
