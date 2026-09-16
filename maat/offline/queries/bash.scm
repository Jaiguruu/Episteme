;; Shell (bash) extraction query.
;;
;; There are no classes or imports in the shell sense. `source`/`.` are commands
;; that pull in another file, so they are captured as @import.module with an
;; #eq? predicate. Every command word is treated as a call target. A shell
;; variable assignment is the closest analogue to a field and is captured as
;; @def.field.

;; --- definitions -----------------------------------------------------------

(function_definition
  name: (word) @name.function) @def.function

(variable_assignment
  name: (variable_name) @name.field) @def.field

;; --- imports ---------------------------------------------------------------

(command
  name: (command_name (word) @_src)
  argument: (word) @import.module
  (#eq? @_src "source"))

(command
  name: (command_name (word) @_dot)
  argument: (word) @import.module
  (#eq? @_dot "."))

;; --- calls -----------------------------------------------------------------

(command_name
  (word) @call.fn)

;; --- documentation ---------------------------------------------------------

(comment) @doc
