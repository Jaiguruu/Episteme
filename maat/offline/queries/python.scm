;; Python extraction query.
;;
;; Convention: every definition pattern captures the whole declaration node
;; with @def.* and its identifier with @name.* in the *same* pattern, so the
;; consumer can pair them per query match. See README.md.

;; --- definitions -----------------------------------------------------------

(class_definition
  name: (identifier) @name.class) @def.class

(module
  (function_definition
    name: (identifier) @name.function) @def.function)

(module
  (decorated_definition
    definition: (function_definition
      name: (identifier) @name.function)) @def.function)

(class_definition
  body: (block
    (function_definition
      name: (identifier) @name.method) @def.method))

(class_definition
  body: (block
    (decorated_definition
      definition: (function_definition
        name: (identifier) @name.method)) @def.method))

;; --- inheritance -----------------------------------------------------------

(class_definition
  superclasses: (argument_list (identifier) @inherit))

;; --- imports ---------------------------------------------------------------

(import_statement
  name: (dotted_name) @import.module)

(import_statement
  name: (aliased_import
    name: (dotted_name) @import.name
    alias: (identifier) @import.alias))

(import_from_statement
  module_name: (dotted_name) @import.module)

(import_from_statement
  name: (dotted_name) @import.name)

(import_from_statement
  name: (aliased_import
    name: (dotted_name) @import.name
    alias: (identifier) @import.alias))

;; --- calls -----------------------------------------------------------------

(call
  function: (identifier) @call.fn)

(call
  function: (attribute
    object: (_) @call.recv
    attribute: (identifier) @call.attr))

;; --- bindings (Stage 6) ----------------------------------------------------
;;
;; A binding records "this name holds this type in this scope", which is what
;; makes `self.repository.save(...)` resolvable at all. Convention:
;;
;;   @bind.name      the bound name            ("repository")
;;   @bind.type      the raw type name         ("PaymentRepository")
;;   @bind.receiver  optional; present for an instance attribute ("self")
;;   @bind.assign    the whole statement, used for the span
;;
;; @bind.type stays raw and unresolved, exactly like @call.fn. Deciding that
;; "PaymentRepository" means `repositories.payment_repository` is Stage 6's job.
;;
;; The `!type` negation keeps these patterns mutually exclusive. Without it,
;; `self.repo: Repo = make()` would match both an annotated pattern and a
;; constructed one, yielding two bindings for one name with different types
;; ("Repo" and "make") and leaving the winner up to match ordering.

;; parameter annotation:  def f(self, repo: PaymentRepository)
;;
;; Captured as @bind.param rather than @bind.name on purpose. Which node type
;; introduces a parameter is language-specific -- Python says `typed_parameter`,
;; TypeScript says `required_parameter`, Java says `formal_parameter` -- and
;; that knowledge belongs in the query, not in a branch in the extractor. The
;; extractor only learns "this is a parameter binding", never why.
(typed_parameter
  (identifier) @bind.param
  type: (type (identifier) @bind.type)) @bind.assign

;; local from a constructed type:  payment = Payment(...)
(assignment
  !type
  left: (identifier) @bind.name
  right: (call function: (identifier) @bind.type)) @bind.assign

;; local aliasing another name:  copy = original
(assignment
  !type
  left: (identifier) @bind.name
  right: (identifier) @bind.type) @bind.assign

;; local with an annotation:  service: Service = make()
(assignment
  left: (identifier) @bind.name
  type: (type (identifier) @bind.type)) @bind.assign

;; instance attribute from a constructed type:  self.service = Service(...)
(assignment
  !type
  left: (attribute
    object: (identifier) @bind.receiver
    attribute: (identifier) @bind.name)
  right: (call function: (identifier) @bind.type)) @bind.assign

;; instance attribute aliasing a name:  self.repo = repo
(assignment
  !type
  left: (attribute
    object: (identifier) @bind.receiver
    attribute: (identifier) @bind.name)
  right: (identifier) @bind.type) @bind.assign

;; instance attribute with an annotation:  self.repo: Repo = make()
(assignment
  left: (attribute
    object: (identifier) @bind.receiver
    attribute: (identifier) @bind.name)
  type: (type (identifier) @bind.type)) @bind.assign

;; --- documentation ---------------------------------------------------------

(module
  . (string) @doc)

(block
  . (string) @doc)

(comment) @doc
