# Guard Grammar for L2

> **Status:** specification `open`. No implementation, no pilot, no guard
> extracted or checked under this grammar. The document fixes what L2 **can**
> and, more importantly, **cannot** verify. This is a derivative translation of
> [`guard-grammar.md`](guard-grammar.md); the Russian text wins on disagreement.
>
> **Normative words.** `MUST`, `MUST NOT`, `SHOULD` follow RFC 2119/8174.
> Anything marked `open` is not a mechanism until evidence exists.

## 1. Why this grammar

L2 regenerates a slice of a formal model from unannotated code and checks
invariants on that slice. Regeneration is only possible if the set of
expressible guard conditions is **bounded**: an infinite language can neither be
extracted reliably nor checked in minutes.

The grammar serves three purposes:

1. **Extractor input.** What counts as a guard and what goes to `unroutable`.
2. **Translator input.** How a guard becomes a model predicate.
3. **Promise boundary.** Which cells L2 closes and which it does not.

The grammar is **not** a programming language, a developer DSL, or an annotation
format. Code stays unannotated; guards are extracted.

## 2. Scope

### 2.1 Covered

- Role- and level-based access (an RBAC/ABAC slice).
- Object-level authorization: comparing subject and object attributes.
- Existence of an attribute or a relation.
- Credential lifetime (TTL) and resource age.
- Composition of these predicates with `and`, `or`, `not`.

### 2.2 Not covered (and required to land in `unroutable`)

- Concurrency: locks, races, check-then-act, fencing tokens.
- Transactions and partial writes, rollback, idempotency.
- Cryptography, signatures, secret comparison.
- Network, retries, timeouts, message delivery.
- Supply chain, build, dependencies.
- Memory, buffer clearing, log leaks.
- Performance and UX.
- Any logic that depends on a value obtained outside the declared context
  (see 7.4).

The boundary is not "complexity" but **observability**: if a condition cannot be
expressed as a predicate over the declared event context, the extractor has no
right to guess.

## 3. Terms

| Term | Meaning |
| --- | --- |
| **Event** | a point where a guard decision is made: `db.invoices.select`, `http.invoices.update`, `job.payout.run` |
| **Context** | a typed description of values available at the event: subject, resource, credentials, time |
| **Guard** | a named condition that permits the event; everything else is denied |
| **Action** | what happens on refusal: `deny`, `abort`, `rollback`, `safe-degrade` |
| **Model** | the set of events and guards regenerated from code |
| **Slice** | a model bounded to changed functions and their reachable dependencies |

## 4. Grammar

### 4.1 File

```ebnf
guard_file   = { declaration } ;
declaration  = context_decl | guard_decl ;

context_decl = "context" ident "{" { field } "}" ;
field        = path ":" type { modifier } ";" ;
type         = "bool" | "int" | "string" | "uuid" | "timestamp"
             | "enum" "{" ident { "," ident } "}"
             | "set" "<" type ">" ;
modifier     = "optional" | "derived" ;

guard_decl   = "guard" ident "on" event ":"
               expr
               "otherwise" action ";" ;
event        = ident { "." ident } ;
action       = "deny" | "abort" | "rollback" | "safe-degrade" ;
```

### 4.2 Expressions

```ebnf
expr         = disjunction ;
disjunction  = conjunction { "or" conjunction } ;
conjunction  = negation { "and" negation } ;
negation     = [ "not" ] primary ;
primary      = "(" expr ")" | predicate ;

predicate    = membership | comparison | existence | age | constant ;
membership   = path "in" "{" value { "," value } "}" ;
comparison   = path cmp value ;
existence    = "exists" "(" path ")" ;
age          = "age" "(" path ")" cmp duration ;
constant     = "true" | "false" ;
cmp          = "==" | "!=" | "<" | "<=" | ">" | ">=" ;

path         = "$" ident { "." ident } ;
value        = literal | path ;
literal      = string | number | boolean | "null" ;
duration     = number ( "s" | "m" | "h" | "d" ) ;
```

### 4.3 Lexical rules

- `ident` is `[A-Za-z_][A-Za-z0-9_]*`.
- `string` uses double quotes, no interpolation.
- `number` is an integer or decimal; negative numbers are allowed only in
  literals, not in paths.
- Comments `//` run to end of line and are not part of the model.
- No user functions, macros, regular expressions, arithmetic, or calls.
  `age(...)` is the only built-in function.

### 4.4 Example

```text
context Request {
  $subject.tenant_id   : uuid;
  $subject.role        : enum {reader, writer, admin};
  $subject.level       : int;
  $resource.tenant_id  : uuid;
  $resource.status     : enum {draft, issued, paid, void};
  $credential.issued_at: timestamp;
}

guard invoice_read on db.invoices.select:
  $resource.tenant_id == $subject.tenant_id
  and $subject.role in {reader, admin}
  and $resource.status != void
otherwise deny;

guard invoice_write on db.invoices.update:
  $resource.tenant_id == $subject.tenant_id
  and $subject.role in {writer, admin}
  and $subject.level >= 2
  and age($credential.issued_at) <= 24h
otherwise deny;
```

## 5. Semantics

### 5.1 A guard is an allow-list

`guard g on e: E otherwise A` means: event `e` is permitted **only** if `E`
holds. If `E` is false or undefined, `A` runs. Absence of a guard for an event
means denial. This is default deny built into the language, not a convention.

### 5.2 Three values

Evaluation is total and three-valued: `true`, `false`, `unknown`.

| Situation | Result |
| --- | --- |
| path absent from the context and not marked `optional` | `unknown` |
| `optional` path absent | `unknown` |
| comparison of different types | `unknown` |
| comparison with `null` using `<`, `<=`, `>`, `>=` | `unknown` |
| `age()` of a missing or future (beyond skew) timestamp | `unknown` |
| `exists()` | `true` or `false`, never `unknown` |
| `not unknown` | `unknown` |

`and`/`or` follow Kleene logic: `unknown and false = false`,
`unknown or true = true`; other combinations with `unknown` yield `unknown`.

**Result:** `unknown` at the root of the expression means denial. An
implementation MUST NOT treat `unknown` as `true` and MUST NOT use short-circuit
evaluation that changes the result.

### 5.3 The negation trap

`not ($resource.tenant_id == $subject.tenant_id)` with a missing `tenant_id`
yields `unknown`, that is, denial. This is correct for an allow-list, but it
means "deny when equal" cannot be written as the negation of a permission. A
denial uses a separate guard with action `deny` and an explicit `exists()`.
Mixing permission and prohibition in one expression is forbidden (see 5.5).

### 5.4 Several guards on one event

If several guards are extracted for one event, they combine by
**deny-overrides**: the event is permitted only if all of them permit it. One
liberal guard cannot override a strict one. This guards against the error where
the extractor found a middleware check and "forgot" the object-level check in
the handler.

### 5.5 No mixed modes

A guard cannot permit and prohibit at the same time. Action `deny` on a true
expression is unsupported: a prohibition uses a separate event or a separate
guard with inverted meaning and an explicit `exists()`. The restriction is
deliberate: mixed modes make the model ambiguous and the proof meaningless.

### 5.6 TTL

`age($path) <= D` requires a trusted clock. The time source, allowed skew, and
behaviour when the label is missing are declared in the extraction manifest.
`age()` of a future label within skew counts as `0`; beyond skew it is
`unknown`. TTL does not prove revocation: it checks only the age of the label.

### 5.7 Levels

`$subject.level` is an integer from a declared domain. `<`, `<=`, `>`, `>=` are
allowed only for `int` and `timestamp`. Levels do not order roles: `role` and
`level` are independent dimensions, and "role OR level" is written explicitly.

## 6. Extractor contract

The extractor is TCB. An extractor bug that loses a guard makes the gate pass on
a leaky model. The contract is therefore stated as obligations, not wishes.

### 6.1 Soundness direction

The model MUST **over-approximate** code behaviour:

```text
E_code ⊆ E_model
∀ e ∈ E_code: Allowed_code(e) ⊆ Allowed_model(e)
```

In guard terms: if the code permits a request, the model must permit it. The
model may permit more (that produces false positives, which is safe) and may not
permit less (that hides a real hole). The reverse direction —
`Allowed_model ⊆ Allowed_code` — is **forbidden**: it turns the gate into a
filter for false comfort.

### 6.2 Three gates

| Gate | Pass condition | Failure |
| --- | --- | --- |
| **Event completeness** | every security event of the changed code is in the model | merge closed |
| **Behaviour refinement** | for every event, `Allowed_code ⊆ Allowed_model` | merge closed |
| **Non-vacuity** | the model is not empty, each target is not degenerate, a reachable denial path exists | merge closed |

Non-vacuity is checked explicitly:

- zero events in the slice is a failure, not "nothing to check";
- a target whose antecedent is trivially `false` is a failure;
- a target whose antecedent is trivially `true` and therefore constrains nothing
  is a failure;
- all events in the slice matching one template while the changed function
  produced no event is a failure.

### 6.3 Extraction manifest

The extractor MUST emit a manifest:

```json
{
  "extractor": {"name": "...", "version": "...", "hash": "sha256:..."},
  "commit": "...",
  "context": {"clock": "...", "skew_seconds": 0},
  "events": [
    {"id": "db.invoices.select", "source": "path/to/file:120-138",
     "guard": "invoice_read", "action": "deny", "confidence": "exact"}
  ],
  "unroutable": [
    {"source": "path/to/file:140-149", "reason": "row-lock",
     "snippet_hash": "sha256:..."}
  ],
  "coverage": {"functions_changed": 0, "functions_extracted": 0}
}
```

`confidence: exact` means the guard was extracted without guessing. Any other
confidence is `unroutable`. The manifest is hashed and enters the verdict
(C-13).

### 6.4 Mutation set

The extractor is checked by mutating code, not only by unit tests. The minimum
set:

| ID | Mutation | Required result |
| --- | --- | --- |
| M1 | add a guard to a previously open function | event appeared, guard extracted |
| M2 | remove a guard | event changed or disappeared |
| M3 | replace `==` with `!=` | predicate changed |
| M4 | narrow the role set | predicate changed |
| M5 | change the TTL | predicate changed |
| M6 | move the check into middleware without a semantic change | event remains, no duplicate |
| M7 | hide the guard in dynamic SQL or a macro | `unroutable`, not a silent skip |
| M8 | wrap the guard in a feature flag | `unroutable` |
| M9 | duplicate the guard | one event, not two |
| M10 | delete the handler entirely | event disappeared, routing changed |

Threshold: **zero silent misses on M1–M5**. M7–M8 MUST produce `unroutable`; a
silent skip is an extractor release failure. M6, M9, M10 are routing
regressions, not soundness.

### 6.5 Versioning

A grammar change is a reviewed change. It requires:

1. recomputing the mutation set;
2. rerunning on the pilot;
3. a claim-registry entry: what became expressible and what stopped being.

Extending the grammar without new evidence is forbidden: otherwise the promise
boundary moves silently.

## 7. Grammar ↔ cell map

All cells come from [`cells.seed.yaml`](cells.seed.yaml).

| Cell | Coverage | What exactly is covered | What remains |
| --- | --- | --- | --- |
| CELL-001 broken-access-control | **yes** | role and tenant guard on every event | platform bypass, superuser, DBA |
| CELL-002 object-level-authorization | **yes** | comparison of object and subject attributes | relations across several tables outside the slice |
| CELL-008 stale-credential | **partial** | label TTL, resource age | actual revocation, session caches |
| CELL-010 batch-bypass | **partial** | only if the batch path calls the same guard | proof of a shared choke point |
| CELL-012 insecure-defaults | **partial** | default deny expressed as a guard | artifact and profile scanning |
| CELL-003 partial-write | **no** | — | transactions, side effects |
| CELL-004 non-idempotent-retry | **no** | — | idempotency keys, delivery |
| CELL-005 check-then-act | **no** | — | locks, isolation |
| CELL-006 stale-worker | **no** | — | fencing tokens, epochs |
| CELL-007 lifecycle-cleanup | **no** | — | cleanup, logs |
| CELL-009 error-contract | **no** | — | error format, leaks |
| CELL-011 supply-chain | **no** | — | build, dependencies |

Rule: **`no` means `unroutable`, not "verified by L2"**. If a configuration
promises L2 coverage for a cell and the cell is `no` in this table, the promise
is false.

## 8. `unroutable` classes

The bucket is not a dump. Each class has a reason and an owner of the decision.

| Class | Example | Why outside the grammar |
| --- | --- | --- |
| `row-lock` | `SELECT ... FOR UPDATE`, `SKIP LOCKED` | depends on scheduler and isolation |
| `check-then-act` | read, then write without a lock | requires a state and race model |
| `dynamic-sql` | condition concatenated into a string | condition is not statically observable |
| `macro-guard` | guard inside a macro or ORM hook | expansion boundary undefined |
| `external-policy` | decision delegated to OPA/service | values arrive outside the context |
| `value-provenance` | tenant taken from a client header | the grammar sees the value, not its source |
| `crypto` | signature check, `hmac.compare_digest` | not a predicate over roles |
| `time-window` | business window, calendar | not TTL and not age |
| `numerical` | limits, quotas, balances | requires arithmetic |
| `feature-flag` | guard enabled by a flag | the model depends on configuration |
| `platform-bypass` | table owner, `BYPASSRLS`, superuser | outside the application model |

Triage quota: an empty bucket signals completeness on the observed stream; a
filling one signals an unknown unknown. Taxonomy expansion is decided by humans
(CONCEPT.md, 5.3).

## 9. Example: RLS on `invoices`

### 9.1 Code

```sql
CREATE TABLE invoices (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  status text NOT NULL,
  owner_id uuid NOT NULL
);

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

CREATE POLICY invoice_read ON invoices
  FOR SELECT
  USING (
    tenant_id = current_setting('app.tenant_id')::uuid
    AND status <> 'void'
  );

CREATE POLICY invoice_write ON invoices
  FOR UPDATE
  USING (
    tenant_id = current_setting('app.tenant_id')::uuid
    AND current_setting('app.role') IN ('writer', 'admin')
  );
```

### 9.2 Model

```text
context Request {
  $subject.tenant_id : uuid;
  $subject.role      : enum {reader, writer, admin};
  $resource.tenant_id: uuid;
  $resource.status   : enum {draft, issued, paid, void};
}

guard invoice_read on db.invoices.select:
  $resource.tenant_id == $subject.tenant_id
  and $resource.status != void
otherwise deny;

guard invoice_write on db.invoices.update:
  $resource.tenant_id == $subject.tenant_id
  and $subject.role in {writer, admin}
otherwise deny;
```

### 9.3 What the example honestly shows

1. **`invoice_read` does not check a role.** That is not a model error: the
   policy genuinely allows any subject of the same tenant to read. If a
   requirement demands a role, the defect is in the policy, not the extractor.
2. **`app.tenant_id` is `value-provenance`.** The grammar sees the comparison
   but not that the value came from a client header. This stays open: even a
   perfect model will not prove the tenant cannot be spoofed.
3. **`FOR UPDATE` is `row-lock`.** The lock is not expressible and lands in
   `unroutable`; concurrency stays with L3 and load testing.
4. **The owner and `BYPASSRLS`** bypass the policy. This is `platform-bypass`
   and a mandatory scope line in the verdict.
5. **`WITH CHECK` is absent.** For `UPDATE`, PostgreSQL uses `USING` for new rows
   as well when `WITH CHECK` is not set; the extractor must know this and must
   not infer "no check" from the absence of `WITH CHECK`. This is an example of
   why the extractor must be platform-specific.

### 9.4 Counterexample: a check exists, but not the right one

```python
@app.get("/invoices/{invoice_id}")
@require_role("reader")
def get_invoice(invoice_id):
    return db.get_invoice(invoice_id)   # no tenant_id check
```

The model will contain `http.invoices.read` with a role guard and will **not**
contain an object guard. The event-completeness gate passes (the event exists);
the behaviour-refinement gate fails: `Allowed_code ⊄ Allowed_model` for the
object cell, because the code permits someone else's `invoice_id`. This is
exactly the defect CELL-002 captures as a separate cell.

## 10. Failure modes of this specification

| Risk | How it shows | Measure |
| --- | --- | --- |
| Extractor as TCB | a lost guard passes silently | mutation set, 6.4 |
| Vacuous model | an empty slice "passes" | vacuity check, 6.2 |
| False precision | `exact` confidence without basis | `unroutable` by default |
| Platform drift | PostgreSQL/ORM changes semantics | platform tests for the extractor |
| Value substitution | tenant from a header | `value-provenance` in scope |
| Language growth for coverage | the grammar grows without evidence | reviewed change, 6.5 |

## 11. Open questions

1. Extractor implementation and its mutation set — phase 2.
2. A pilot on a real codebase; without it every L2 cost estimate is a
   hypothesis.
3. Formal semantics of three-valued logic in the target verifier (`probcli`,
   Z3): how `unknown` is encoded as a predicate.
4. A minimal event set for non-SQL layers (HTTP routers, gRPC, queues).
5. Policy for `feature-flag`: treat configuration as part of the code or as
   `unroutable`.
6. How an L2 verdict links to the claim registry: which claim a covered cell
   closes.

## 12. What would change this document

The specification stops being `open` when:

- the extractor passes mutation set M1–M10 with zero silent misses;
- extraction precision/recall against manual labelling is measured on a pilot;
- the vacuity gate fires on an injected empty model;
- at least one cell from the section 7 map reaches a status above `open` with a
  verdict and scope.

Until then this document is a promise boundary, not a promise.
