;; Ruby extraction query.
;;
;; `require` and `require_relative` are ordinary method calls with a string
;; argument, so imports are captured with an #eq? predicate on the method name.
;; Ruby's `def` is a `method` node whether it sits at the top level or in a
;; class, so every definition is captured as @def.method.
;;
;; The `.` anchor on the direct-call pattern keeps a receiver call from also
;; being captured as @call.fn.

;; --- definitions -----------------------------------------------------------

(class
  name: (constant) @name.class) @def.class

(singleton_class
  value: (_) @name.class) @def.class

(module
  name: (constant) @name.module) @def.module

(method
  name: (identifier) @name.method) @def.method

(singleton_method
  name: (identifier) @name.method) @def.method

;; --- inheritance -----------------------------------------------------------

(class
  (superclass (constant) @inherit))

;; --- imports ---------------------------------------------------------------

(call
  method: (identifier) @_req
  arguments: (argument_list (string (string_content) @import.module))
  (#eq? @_req "require"))

(call
  method: (identifier) @_req
  arguments: (argument_list (string (string_content) @import.module))
  (#eq? @_req "require_relative"))

;; --- calls -----------------------------------------------------------------

(call
  . method: (identifier) @call.fn)

(call
  receiver: (_) @call.recv
  method: (identifier) @call.attr)

;; --- documentation ---------------------------------------------------------

(comment) @doc
