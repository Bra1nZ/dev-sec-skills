# Missing Negative Test Plan: Django Money Transfer

## 0. Verdict on the current suite

A green suite containing happy paths and a few 400-response cases does **not** support either claim.

It is evidence only that some single-request validation paths work. Both claims are **concurrency and state-invariant claims**, and neither can be established by sequential request/response tests:

1. "No double spending under concurrent retries" requires proving **at-most-once execution per logical transfer** and **serializable balance effects** across simultaneous requests, including retries after ambiguous timeouts.
2. "Balance can never go negative" requires proving a **database-enforced invariant** that holds during every intermediate state, not merely that one handler rejects an obviously oversized amount.

The missing plan below is deliberately adversarial. Passing it is necessary evidence; it is still not absolute proof unless the database constraints and transaction semantics described in §7 are actually in place.

---

## 1. Define the claims precisely before testing

Ambiguous claims cannot be falsified. Pin these down in the test docstring or spec:

- **Logical transfer identity**: a client-supplied idempotency key (or equivalent request ID) identifies one transfer. Retries with the same key are the same logical transfer.
- **At most once**: for a given idempotency key, at most one debit/credit pair is committed, regardless of how many concurrent or sequential retries arrive.
- **At least once delivery / retry semantics**: a retry after a lost response must return the original result, not execute again.
- **No double spending**: the sum of committed debits for an account never exceeds its available balance, and no single logical transfer is applied more than once.
- **Balance non-negative**: for every account, at every committed database state, `balance >= 0` (and `available_balance >= 0` if holds exist).
- **Money representation**: integer minor units or `Decimal`; floats are a defect. Define rounding and currency rules.

If the endpoint has no idempotency key, claim (1) is not achievable for client retries; a test should record that as a product gap rather than passing.

---

## 2. Test environment requirements (otherwise the tests are theatre)

- Use the **real production database engine** (typically PostgreSQL), not SQLite. SQLite's locking and isolation behaviour will hide row-lock and serialization bugs.
- Concurrency tests must use **separate database connections** and real threads or processes. Django's `TransactionTestCase` (not `TestCase`, which wraps each test in one transaction) is required; close connections in each worker.
- Do **not** run concurrency assertions inside a test transaction that is rolled back at the end; workers need to see each other's commits.
- Use `select_for_update()` / atomic conditional updates if that is the implementation; tests must exercise the actual production path, not a mock.
- Reset data between cases; use unique account IDs per test to avoid cross-test interference.
- Record DB state before and after, plus server logs/query counts where relevant.

---

## 3. Idempotency and retry tests (claim 1, part A)

### IT-1 — Sequential retry with the same key

**Setup**: Account A balance 100, account B balance 0. POST transfer 30 with `Idempotency-Key: k1`.
**Action**: Send the identical request again (same key, same payload).
**Assert**:
- Second response status is the same successful status (or a documented `200` replay), not a second execution.
- A balance 70, B balance 30 after both requests.
- Exactly one transfer record and exactly one debit/credit ledger pair for `k1`.
- Response body for the replay is byte-equivalent or field-equivalent to the first (at minimum same transfer ID and amount).
- No second `INSERT` of a ledger row (count query).

### IT-2 — Concurrent retries with the same key

**Setup**: A=100, B=0. Launch 20 threads, synchronized by a `threading.Barrier`, all POST the same 30 transfer with key `k1`.
**Assert**:
- Exactly one distinct transfer ID across all responses.
- A=70, B=30, never 40/60 or any multiple debit.
- Exactly one committed ledger debit and one credit.
- Responses are either the same success result or documented conflict/duplicate responses; **none** show a second successful debit.
- No unhandled 500s; no unique-constraint error leaking as a 500 (it should be translated to a replay/conflict).

### IT-3 — Same key, different payload

**Setup**: Successful transfer with key `k1` for 30.
**Action**: Retry key `k1` with amount 50, or different destination.
**Assert**:
- Rejected with `409 Conflict` or documented `422`; no balance change.
- Original transfer remains intact.
- This prevents an idempotency-key collision from silently changing the operation.

### IT-4 — Retry after lost/ambiguous response (timeout injection)

**Setup**: Make the first request commit the transfer, then simulate the client not receiving the response (raise/timeout after DB commit, or use a proxy that drops the response). Client retries with the same key.
**Assert**:
- Exactly one committed transfer and one debit/credit pair.
- Retry returns the original result.
- This is the core "concurrent retry" case: commit succeeded but the client believes it failed.

### IT-5 — Retry after server crash between debit and credit

**Setup**: Inject an exception after the debit `save()` but before the credit, inside the atomic block (mock/patch a collaborator or use a test hook).
**Assert**:
- Transaction rolls back completely: neither balance changes, no ledger rows, no transfer row marked successful.
- If the implementation uses a two-phase state machine (`pending` then `completed`), assert the pending record is handled by recovery and is not counted as spent.
- A subsequent retry with the same key either completes once or is safely rejected; it never partially applies.

### IT-6 — Retry after a 500/timeout from a downstream dependency

**Setup**: Make an external call (notification, ledger service, FX service) fail on the first attempt and succeed on retry.
**Assert**:
- The money movement is not repeated if it already committed.
- If the whole operation rolled back, the retry commits exactly once.
- No "debit committed, credit rolled back" state.

### IT-7 — Idempotency-key lifecycle

**Setup**: Same key reused after the original transfer is old/expired, or key scoped per user vs globally.
**Assert**:
- Documented behaviour is enforced (expired key may be treated as new only if the old transfer is final and the spec says so; otherwise reject).
- Keys are scoped to the authenticated principal; user X cannot replay/suppress user Y's key.
- Empty/oversized/Unicode keys are rejected with 400, not 500.

**Evidence for claim 1, part A**: a unique database constraint on `(principal, idempotency_key)` or an equivalent insert-if-absent mechanism, plus test output showing one row per key under 20-way concurrency. Without a DB-level uniqueness guarantee, application-level "check then insert" is racy and the claim is not justified.

---

## 4. Concurrency and serialization tests (claim 1, part B; claim 2, part B)

### CT-1 — Concurrent debits that together exceed the balance

**Setup**: One source account A=100, many destinations. 20 threads each try to transfer 10 with **distinct** idempotency keys, synchronized by a barrier.
**Assert**:
- Exactly 10 succeed, 10 fail with `409/422` (insufficient funds), never 11 successes.
- Final A=0 (or the exact expected value), never negative.
- Sum of successful debits = 100; sum of credits = 100.
- No lost updates: final balance is not 90/80/etc. because of read-modify-write races.
- Failed requests have no ledger rows and no partial credit to destinations.
- Run repeatedly (e.g. 20 iterations) to catch flakiness.

### CT-2 — Concurrent transfers in both directions (deadlock/ordering)

**Setup**: A=100, B=100. Half the threads transfer A→B, half B→A, same or small amounts, synchronized.
**Assert**:
- No deadlock surfaces as a 500; either requests succeed or are retried by the app, or a documented `409` is returned.
- Final A+B = 200 exactly (conservation of money).
- No negative balances at any point (query after each iteration; also see CT-6).
- Lock ordering is consistent; if deadlocks are expected, the app retries them and the test asserts eventual success without duplicate execution.

### CT-3 — Concurrent retries of the same transfer while other transfers run

**Setup**: Combine IT-2 and CT-1: 10 distinct logical transfers, each retried 3 times concurrently, total requested > balance.
**Assert**:
- Exactly one execution per distinct key.
- Total committed debits never exceed the initial balance.
- No duplicate credits.
- This is the closest test to the literal claim "no double spending under concurrent retries".

### CT-4 — Concurrent exact-balance boundary

**Setup**: A=100. 10 threads each transfer 100 with distinct keys.
**Assert**:
- Exactly one succeeds; nine fail; A=0, never negative.
- This catches the classic `if balance >= amount` race where two requests both read 100.

### CT-5 — Concurrent transfers involving fees/holds

**Setup**: If the endpoint charges a fee or creates a hold, run concurrent transfers where `amount + fee` exceeds balance but `amount` alone does not.
**Assert**:
- The effective debit (`amount + fee`, or held amount) is what is checked atomically.
- No negative available balance.
- Holds are released exactly once on failure/retry.

### CT-6 — Invariant sampling during the run

**Setup**: While CT-1/CT-2/CT-3 run, a separate observer connection polls all involved accounts and ledger sums in a loop.
**Assert**:
- Every observed committed state has `balance >= 0`.
- Ledger sum equals balance according to the accounting model (e.g. credits − debits = balance, or opening + movements).
- No state where a debit exists without a matching credit in a completed transfer.
- Note: with `READ COMMITTED`, the observer may see intermediate transactions; the assertion is about committed states, so document the isolation level and avoid claiming more than it proves.

### CT-7 — Isolation-level test

**Setup**: Run CT-1/CT-4 at the isolation level configured in production (`READ COMMITTED`, `REPEATABLE READ`, or `SERIALIZABLE`).
**Assert**:
- The chosen isolation level plus locking/conditional update actually prevents write skew and lost updates.
- If the app relies on `SERIALIZABLE`, assert serialization failures are retried and do not become duplicate executions.
- A test that passes only under `SERIALIZABLE` while production uses `READ COMMITTED` is not evidence.

**Evidence for claim 1, part B**: concurrency traces showing `N` attempts, `K` successes, exact expected balances, unique ledger rows, and DB constraints (unique key, non-negative check) present in migrations. Also evidence that the balance update is a single atomic statement or a properly locked read-modify-write, not an unlocked ORM read followed by `save()`.

---

## 5. Balance non-negative tests (claim 2, part A)

### NB-1 — Amount greater than balance

A=50, transfer 50.01 (or 51). Assert `400/409/422`, A unchanged, no ledger/transfer rows, no credit to destination.

### NB-2 — Amount equal to balance

A=50, transfer 50. Assert success, A=0 exactly, destination +50. Boundary is inclusive; `>=` vs `>` bugs are common.

### NB-3 — Zero amount

Assert rejected with 400 (unless explicitly allowed as a no-op, in which case assert no ledger rows and unchanged balances). Zero must not create a zero-value ledger entry that breaks invariants.

### NB-4 — Negative amount

Transfer `-10` from A to B. Assert 400 and that it is **not** interpreted as a reverse transfer (which would credit A and debit B). Also test negative amount with a positive-looking idempotency key and with decimal strings such as `"-0.01"`.

### NB-5 — Precision and rounding boundaries

Using `Decimal`/minor units:
- A=0.10, transfer 0.10 succeeds to exactly zero.
- A=0.10, transfer 0.1000000001 rejected, not rounded into an overdraft.
- Amounts with more decimal places than the currency allows are rejected or rounded per documented rule, and the resulting debit matches the ledger exactly.
- Large values near `DecimalField(max_digits, decimal_places)` limits: overflow returns 400, not a 500 or a wrapped/truncated value.
- Float artifacts: `0.1 + 0.2` style cases must not create a balance of `-1e-17` or a false rejection.

### NB-6 — Same-account transfer

A→A for any amount. Assert either 400 or a well-defined no-op with unchanged balance; never a debit/credit pair that can be exploited for rounding or fee manipulation.

### NB-7 — Currency mismatch / missing currency

Transfer USD from a EUR account, or omit currency. Assert 400, no balance change. If FX is supported, assert conversion uses one consistent rate and the invariant still holds after rounding.

### NB-8 — Inactive/frozen/closed account

Attempt from an account with status `frozen`, `closed`, or `kyc_pending`. Assert 409/403/400 per policy and no balance change. If frozen accounts can receive but not send, test both directions.

### NB-9 — Unknown or unauthorized source/destination

- Nonexistent account ID → 400/404, no partial state.
- Destination belongs to another user and the caller lacks permission → 403, no debit.
- Source account not owned by caller → 403/404, no debit.
- (These are not strictly the balance claim, but a debit-then-fail-authorization path would violate it.)

### NB-10 — Reversal/refund cannot over-credit

If reversals exist, reverse a completed transfer twice. Assert the second reversal is rejected or idempotent; destination cannot be credited twice, source cannot go below zero on a reversal that is actually a new debit.

**Evidence for claim 2, part A**: a DB `CHECK (balance >= 0)` constraint (or equivalent trigger) in the schema, plus handler tests proving the check is inside the same transaction as the update. If only the application checks, a concurrent or alternate code path can still violate it.

---

## 6. Transaction, failure-injection, and property tests

### FT-1 — Exception after debit rolls back the credit

Covered by IT-5; repeat for exceptions in serializers, signals, and post-save hooks. Assert no partial commit.

### FT-2 — Process kill / connection loss mid-transaction

Simulate a worker being killed after the debit statement but before commit (e.g. `os._exit` in a subprocess or a DB connection drop). Assert the DB contains no partial transfer and the retry behaves per IT-4/IT-5.

### FT-3 — Deadlock retry does not duplicate

Force a deadlock between two transfers (opposite lock order in a controlled test) and assert the retry succeeds once, with conservation of money and no duplicate ledger rows.

### FT-4 — Duplicate delivery at the queue/worker level

If transfers are processed asynchronously, enqueue the same message twice (and concurrently). Assert the consumer's idempotency handling yields one effect. Include redelivery after ack loss.

### FT-5 — Property-based / model-based test

Generate random sequences of transfers (valid and invalid amounts, random accounts, random idempotency keys, duplicates, retries) and run them concurrently. After each run assert:
- For every account: `balance >= 0`.
- For every completed transfer: exactly one debit and one credit of the same amount.
- Total money in the system is conserved (minus explicitly modeled fees).
- Sum of ledger movements reconciles with balances.
- Replaying any subsequence of requests with the same idempotency keys does not change final state.

Use Hypothesis (or equivalent) to shrink failing sequences; run enough examples to exercise interleavings, and keep the seed in CI output.

### FT-6 — DB constraint tests (direct SQL)

Bypass the application and attempt:
- `UPDATE account SET balance = -1` → must fail with an integrity error.
- Insert a duplicate `(principal, idempotency_key)` → must fail with a unique violation.
- Insert a ledger row with a negative amount where the schema forbids it → must fail.
These prove the invariant is enforced below the handler, which is what makes the claim credible against future code paths.

### FT-7 — Conservation under failure

Run the concurrency suite with random injected failures (timeouts, 500s, deadlocks). Assert that for every account, the final balance equals opening balance plus the sum of committed ledger movements, and that no money is created or destroyed.

---

## 7. What evidence would actually justify each claim

### To justify "no double spending under concurrent retries"

Collect and attach:

1. **Schema evidence**: migration/schema showing a unique constraint on the idempotency key (scoped to the principal) and a non-negative balance check constraint.
2. **Code evidence**: the transfer handler performs the balance mutation and the idempotency insert in one transaction, using either a conditional atomic `UPDATE ... WHERE balance >= amount` or `SELECT ... FOR UPDATE`, not an unlocked read-check-write.
3. **Concurrency evidence**: CI output from IT-2, IT-4, CT-1, CT-3, CT-5 showing exact expected success counts, exact final balances, one transfer row per key, and one debit/credit pair per successful transfer, over repeated runs (e.g. 20+ iterations).
4. **Failure evidence**: IT-5/FT-1/FT-2 showing full rollback on injected exceptions/crashes and safe retry afterward.
5. **Negative evidence**: IT-3 (same key, different payload), IT-7 (key scoping/expiry), and duplicate-delivery tests showing no silent second effect.

Anything less — especially only sequential retry tests or mocks without real DB transactions — supports "idempotent in the happy path", not the claim.

### To justify "balance can never go negative"

Collect and attach:

1. **DB constraint evidence**: `CHECK (balance >= 0)` (and for available balance if holds exist) present in the schema, with FT-6 proving direct SQL cannot violate it.
2. **Atomicity evidence**: the check and the update occur in one transaction with row locking or a conditional update; CT-4's exact-balance race passes repeatedly at the production isolation level.
3. **Boundary evidence**: NB-1 through NB-6, NB-9, and the precision cases, each showing no state change on rejection.
4. **Concurrency evidence**: CT-1, CT-2, CT-6 with invariant sampling showing `balance >= 0` in every observed committed state and money conservation.
5. **Failure evidence**: FT-1, FT-2, FT-7 showing rollback and conservation under exceptions/crashes.

The claim is only as strong as the lowest-level enforcement. If the non-negative check exists only in Python, the claim should be downgraded to "the tested handler rejects overdrafts", not "balance can never go negative".

---

## 8. Gaps in the current suite, summarized

- No idempotency-key tests at all (sequential, concurrent, payload mismatch, expiry, scoping).
- No true concurrency tests with separate DB connections/transactions.
- No tests for the lost-response/commit-then-timeout retry case.
- No rollback/failure-injection tests.
- No DB-level constraint tests or schema assertions.
- No exact-boundary, zero, negative, precision, overflow, or same-account cases.
- No invariant/conservation checks during or after concurrent runs.
- No deadlock or serialization-failure retry tests.
- No property-based stress test.
- "Few 400-response tests" likely assert only status codes; they should also assert **no state change** and **no side effects**.

## 9. Minimum CI gate before making the claims

Run the following on PostgreSQL with real concurrent connections, at the production isolation level, 20 iterations each:

- IT-2, IT-4, IT-5, IT-3
- CT-1, CT-3, CT-4, CT-6
- NB-1, NB-2, NB-4, NB-5, NB-6
- FT-1, FT-6, FT-7

If any of these is flaky, the correct conclusion is **not yet proven**, regardless of the rest of the suite being green.
