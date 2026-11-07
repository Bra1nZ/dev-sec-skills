# Invariant Catalogue Outside Databases and Roles

`spec/invariants/catalog.yaml` (V2-21) answers a different question from the
cell registries. A cell records a failure class that a detector exercises; an
invariant records what must always be true, where it is enforced, what
observation distinguishes a violation, and which bypasses are known. The
catalogue covers the five general-code categories that the RBAC pilots do not:
input validation, authentication/session, secrets, lifecycle, transactions.

It is design knowledge, not evidence. Every entry starts `open`. Naming a
negative test does not mean the test exists, has run, or is sensitive to the
guard. `tools/invariant_catalog.py` checks internal consistency and
traceability; it cannot check that an invariant holds.

## Files

- `catalog.yaml` — 5 categories, 15 invariants, `out_of_scope` seed cells.
- `2026-11-07-coverage.json` — recorded coverage snapshot from the validator.
- `schemas/invariant-catalog.schema.json` — field contract and enums.
- `tools/invariant_catalog.py` — INV1–INV5.
- `evals/invariant-catalog/` — 15 synthetic adversarial cases.

## Checks

| Check | Fires when |
| --- | --- |
| INV1 categories | a category is missing or extra, has fewer than two invariants, or lacks a title/class/failure/description |
| INV2 shape | an entry lacks a required field, has a duplicate ID, an ID whose prefix disagrees with its category, an `other` class or mode, fewer than two bypasses, or an unknown status/evidence kind |
| INV3 references | a category, seed cell, choke-point rule or `out_of_scope` cell does not exist, or a cell is both referenced and out of scope |
| INV4 evidence | a non-open entry has no `evidence_path`, or the path does not exist |
| INV5 coverage | a seed cell is neither referenced nor in `out_of_scope`; unused rules are reported as info |

Exit codes: `0` no errors, `1` errors, `2` tool or input error.

References resolve against `spec/conveyor/cells.seed.yaml` and
`spec/choke-points/rules.yaml`. The cell schema supplies the `taxonomy_class`
and `failure_mode` enums, so the catalogue cannot quietly introduce a class
outside the taxonomy. `other` is rejected: the catalogue is not an escape hatch.

## Coverage snapshot (2026-11-07)

`make invariants-record` writes `2026-11-07-coverage.json`.

| Category | Invariants | Seed cells |
| --- | --- | --- |
| input validation | 3 | CELL-009, CELL-010 |
| authentication/session | 3 | CELL-008 |
| secrets | 3 | CELL-007, CELL-008, CELL-009, CELL-012 |
| lifecycle | 3 | CELL-006, CELL-007, CELL-009 |
| transactions | 3 | CELL-003, CELL-004, CELL-005, CELL-006 |

`INV1`–`INV4`: 0 errors. The seed has 12 cells: 9 are referenced and 3 are
listed out of scope (CELL-001 and CELL-002 are database roles, CELL-011 is
supply chain). Of the 11 choke-point rules, 9 are used; the two unused rules
are `sql-rls` (database-specific) and `migration` (not one of the five
categories). They are reported as info, not forced into the catalogue.

All 15 entries are `open`: no pilot detector cites them, and the negative tests
are specifications. The snapshot is a map of obligations and a traceability
check, not a coverage percentage for a product.

## Limits

The validator checks that references exist, not that the referenced rule or
cell means what the invariant says. `failure_class` is a free string in the
cell schema, so a typo is not caught. Two bypasses are a minimum, not a threat
model: a real bypass can be unknown, which is precisely why the entry stays
open.

The catalogue deliberately excludes database role and grant enforcement and
supply-chain integrity. Adding a category is a taxonomy change, not an edit:
the schema and this file must change together.

## Adding an invariant

1. Pick a category and a failure class that already routes in
   `spec/choke-points/rules.yaml`; if no rule fits, add the rule first and
   measure its noise.
2. Write a falsifiable statement and one enforcement point. If the check is
   duplicated in handlers, the enforcement point is not one.
3. Name the observation that distinguishes a violation and the response.
4. Write the negative test that must fail when enforcement is removed, and at
   least two bypasses.
5. Link the seed cell. If the cell is outside the five categories, add it to
   `out_of_scope` with a reason rather than leaving it silent.
6. Keep `status: open` until a detector in a pilot cites the invariant and a
   run record exists.
