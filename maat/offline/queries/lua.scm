;; Lua extraction query.
;;
;; Lua has no classes. `function PaymentService.new()` (dot index) and
;; `function PaymentService:process()` (method index) are the idiomatic
;; constructor/method forms and map to @def.method; a plain `function f()` is
;; @def.function.
;;
;; `require("mod")` is an ordinary function call, so imports are captured with
;; an #eq? predicate on the callee name.

;; --- definitions -----------------------------------------------------------

(function_declaration
  name: (identifier) @name.function) @def.function

(function_declaration
  name: (dot_index_expression
    table: (identifier)
    field: (identifier) @name.method)) @def.method

(function_declaration
  name: (method_index_expression
    table: (identifier)
    method: (identifier) @name.method)) @def.method

;; --- imports ---------------------------------------------------------------

(function_call
  name: (identifier) @_req
  arguments: (arguments
    (string content: (string_content) @import.module))
  (#eq? @_req "require"))

;; --- calls -----------------------------------------------------------------

(function_call
  name: (identifier) @call.fn)

(function_call
  name: (dot_index_expression
    table: (_) @call.recv
    field: (identifier) @call.attr))

(function_call
  name: (method_index_expression
    table: (_) @call.recv
    method: (identifier) @call.attr))

;; --- documentation ---------------------------------------------------------

(comment) @doc
