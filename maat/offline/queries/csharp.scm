;; C# extraction query.

;; --- definitions -----------------------------------------------------------

(class_declaration
  name: (identifier) @name.class) @def.class

(struct_declaration
  name: (identifier) @name.class) @def.class

(record_declaration
  name: (identifier) @name.class) @def.class

(interface_declaration
  name: (identifier) @name.interface) @def.interface

(enum_declaration
  name: (identifier) @name.enum) @def.enum

(method_declaration
  name: (identifier) @name.method) @def.method

(constructor_declaration
  name: (identifier) @name.constructor) @def.constructor

(property_declaration
  name: (identifier) @name.field) @def.field

(field_declaration
  (variable_declaration
    (variable_declarator
      name: (identifier) @name.field))) @def.field

(namespace_declaration
  name: (identifier) @name.module) @def.module

(namespace_declaration
  name: (qualified_name) @name.module) @def.module

;; --- inheritance -----------------------------------------------------------

(class_declaration
  (base_list (identifier) @inherit))

(interface_declaration
  (base_list (identifier) @inherit))

;; --- imports ---------------------------------------------------------------

(using_directive
  (identifier) @import.module)

(using_directive
  (qualified_name) @import.module)

;; --- calls -----------------------------------------------------------------
;;
;; `this.M()` carries no `expression` child (the `this` keyword is anonymous),
;; so it is matched by the leading-name form; `obj.M()` by the receiver form.
;; The `.` anchor keeps the two forms from overlapping.

(invocation_expression
  function: (identifier) @call.fn)

(invocation_expression
  function: (member_access_expression
    . name: (identifier) @call.attr))

(invocation_expression
  function: (member_access_expression
    expression: (_) @call.recv
    name: (identifier) @call.attr))

;; --- documentation ---------------------------------------------------------

(comment) @doc
