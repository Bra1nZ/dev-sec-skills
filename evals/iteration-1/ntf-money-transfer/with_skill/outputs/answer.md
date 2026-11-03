# Negative-First Review: Django Money Transfer

## 0. Bottom line

The current evidence is: happy-path tests pass, and a few tests return 400 on bad input. That is **not evidence for either claim**. A green happy path proves the nominal path; a 400 proves only that something rejected something. Neither test has tried to violate the rule.

| Claim as currently worded | Status now | What is missing |
|---|---|---|
| "No double spending under concurrent retries" | **UNPROVEN** | No test sends the same logical transfer concurrently, replays a completed request, retries after a lost response, or exercises duplicate queue delivery. No idempotency mechanism is demonstrated. |
| "Balance can never go negative" | **UNPROVEN** | No test transfers exactly the balance, one minor unit past it, or races multiple debits that are individually affordable but collectively exceed the balance. No test proves a database constraint or checks all write paths. |

Do not put either sentence in a README, release note, or incident report yet. After the blocking tests below pass, the honest claim is scoped to the tested database, isolation level, entry points, and retry window. Until then the claims are `UNPROVEN`, not "partially covered."

The two claims must be split because they fail differently:

- **C1** is about *identity and repetition*: the same logical transfer must commit at most once.
- **C2** is about *aggregate value*: distinct transfers must never move an account below zero.

A system can pass C1 and fail C2 (no idempotency needed for two different transfers that overdraw together). A system can pass C2 and fail C1 (each duplicate is individually affordable, so the balance never goes negative, but the customer is debited twice). Test both, and test them together.

---

## 1. Claim ledger: what must be violated before it can be claimed

| ID | Exact claim to earn | Mechanism that must exist | Negative test that attempts the violation | Status |
|---|---|---|---|---|
| **C1** | For one authenticated principal and one idempotency key, at most one transfer is committed and at most one debit/credit pair is posted, even if the request is delivered concurrently, retried, replayed after a lost response, or redelivered by a queue. | Client- or server-supplied idempotency key; unique constraint on `(principal, idempotency_key)`; atomic insert of the key plus the financial rows; replay returns the stored result; retention at least as long as the supported retry window. | `C1-02`, `C1-03`, `C1-07`, `C1-10`, `C1-17` | **UNPROVEN** |
| **C2** | For every account, after every committed operation, `balance >= 0`; a transfer whose amount plus fees exceeds the available balance is refused before any financial write. | Application check plus an atomic conditional update or correct row locking; a database `CHECK` constraint as defense in depth; every write path routed through the same invariant. | `C2-02`, `C2-06`, `C2-07`, `C2-09`, `C2-11`, `C2-13` | **UNPROVEN** |
| **C1.1** | A replay of a completed request returns the original result and does not move money again. | Stored response/transfer ID; idempotency record committed with the transfer. | `C1-01`, `C1-03` | **UNPROVEN** |
| **C1.2** | A retry after a timeout where the first attempt committed does not create a second transfer. | Atomic commit of transfer and idempotency record; retry path finds the record. | `C1-03`, `C1-03b` | **UNPROVEN** |
| **C1.3** | A retry after a failure where the first attempt rolled back succeeds exactly once. | No orphaned "in progress" idempotency row; idempotency state is consistent with the rolled-back transaction. | `C1-04` | **UNPROVEN** |
| **C1.4** | Two different clients/workers cannot both commit the same key. | Database uniqueness, not an in-process `threading.Lock`. | `C1-02`, `C1-17` | **UNPROVEN** |
| **C2.1** | Transfer exactly equal to the balance succeeds and leaves zero. | Correct inclusive comparison and atomic update. | `C2-01` | **UNPROVEN** |
| **C2.2** | One minor unit past the balance is refused with no partial write. | `balance >= amount` check and transaction rollback. | `C2-02`, `C2-08` | **UNPROVEN** |
| **C2.3** | Concurrent distinct debits cannot collectively overdraw. | `SELECT ... FOR UPDATE` on all involved rows with deterministic lock order, or a conditional `UPDATE ... WHERE balance >= amount`. | `C2-06`, `C2-07`, `C1-07` | **UNPROVEN** |
| **C2.4** | No supported entry point can persist a negative balance. | DB `CHECK` constraint plus service-layer guard; admin, batch, worker, and ORM paths audited. | `C2-09`, `C2-11`, `C2-12` | **UNPROVEN** |
| **C2.5** | The ledger and balances remain mutually consistent after every success, refusal, and rollback. | Double-entry ledger; balance derived from or reconciled with movements; atomic transaction. | `C2-14`, `C2-15` | **UNPROVEN** |

A claim with no row above that names a violating test is a hope, not coverage. Keep this table in the repository as the traceability index. `UNPROVEN` must not be silently changed to `PASS` because the happy path is green.

---

## 2. Gap review of the current suite

The description tells us only that the suite contains happy-path tests and a few 400-response tests. Evaluate the actual suite against this checklist; anything not found is a gap.

| Check in the current tests | If absent, what it means |
|---|---|
| A test sends two requests with the same idempotency key, one after the other. | C1 is not even attempted. Sequential replay is the cheapest negative and must exist before concurrency. |
| A test sends N requests with the same key at the same time behind a barrier. | Concurrent duplicate protection is unproven; the check-then-insert race is exactly what a single-threaded test cannot catch. |
| A test simulates a commit followed by a lost response and then retries. | The most common real double-spend path is untested. |
| A test sends distinct concurrent debits whose sum exceeds the balance. | C2 is unproven under concurrency; two individually valid transfers can both pass a read-then-write check. |
| A test uses `amount == balance` and `amount == balance + 0.01` (or one minor unit past). | The boundary and off-by-one are untested. The rule can be off by one in either direction. |
| A test tries negative and zero amounts, wrong types, `NaN`/`Infinity`, too many decimal places, and oversized values. | Input classes are not enumerated; random bad inputs can miss the sign and rounding cases. |
| Every refusal test asserts that balances, transfer rows, ledger rows, and outbox events did not change. | A 400 response alone does not prove the rule ran; the service may have written before failing. |
| Every refusal test asserts an exact application error code and the layer that refused. | `assert response.status_code == 400` cannot distinguish application refusal from serializer refusal, database refusal, or a typo. |
| A test attempts the same overdraft through the service function, admin, management command, Celery task, bulk import, reversal/refund, and direct ORM. | The claim "balance can never go negative" is only endpoint-local; another writer can bypass it. |
| A direct `UPDATE`/`save()` test proves a DB `CHECK (balance >= 0)` exists. | If only the application checks, any other writer, migration, or manual operation can create a negative balance. |
| Tests run on PostgreSQL with `TransactionTestCase` / `transaction=True`, not SQLite. | SQLite serializes writes and makes `select_for_update()` a no-op; a green concurrency test there is not evidence. |
| A mutation removes the idempotency unique constraint, the balance check, the row lock, and the atomic block, and the relevant test fails. | A test artifact is not evidence that the test can fail. Without mutation evidence, the verifier is unverified. |
| The CI job records database version, isolation level, worker count, and repeat count. | "It passed once" is not a concurrency result. Race tests are probabilistic and need repetition and environment detail. |

### What the current green suite actually proves

- Happy path: a valid transfer can succeed in the tested environment. It says nothing about duplicate delivery, concurrency, boundaries, or other entry points.
- The 400 tests: at least one invalid input is rejected somewhere. They do not prove the service reached the balance check, that the correct error code/layer was used, or that no rows were written before the error.
- "All tests pass": this is a statement about the tests that exist, not about the claims. Coverage theater is 100% line coverage with zero rejection inputs.

---

## 3. Preconditions: without these, the test results are not evidence

1. **Use PostgreSQL** (the production engine and version, or a pinned supported matrix). Run concurrency tests against a real server, not SQLite. Record `SELECT version()` and `SHOW default_transaction_isolation;`.
2. **Use `TransactionTestCase`** (pytest: `@pytest.mark.django_db(transaction=True)`) for thread/process tests. Django `TestCase` wraps each test in a transaction, and other threads do not see the test's uncommitted rows.
3. **Give each worker its own connection and close it in `finally`.** Do not share a Django `APIClient` or connection object across threads. For HTTP-level tests, use a live server and separate clients; for service-level tests, call the use case directly.
4. **Synchronize the start** with `threading.Barrier` (or a process barrier). Starting threads in a loop is not a race test; the first request may finish before the second begins.
5. **Repeat nondeterministic tests.** A minimum of 100 iterations for the P0 race cases, with a fresh account and key per iteration. Report the iteration count; do not retry a failing iteration until it goes green.
6. **Do not swallow thread exceptions.** Capture every exception and attach it to the test failure; a background thread that dies silently can make the test look green.
7. **Assert from a fresh connection after joins.** Do not trust an in-memory object or a cached balance; query the database after all workers finish.
8. **Inject failures at defined points**, not with a random `sleep()`. Use a monkeypatched hook or a test-only failpoint: before commit, after debit before credit, after commit before response, after response serialization.
9. **Freeze or control time** for idempotency-expiry and retry-window tests.
10. **Use decimal money, never floats.** The test data should be in minor units or `Decimal` with an explicit scale; the database column should be `numeric`/`DecimalField`, not `float`.

If CI only has SQLite, the concurrency claim is **UNPROVEN**, not "skipped and assumed." Mark it as an open release risk in the evidence record. A silent skip is an anti-pattern.

### Recommended minimal harness

```python
import threading
from concurrent.futures import ThreadPoolExecutor
from django.db import connections


def run_concurrently(n, fn):
    """Run fn(i) in n threads that start together. Return (i, result, exception)."""
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        try:
            barrier.wait(timeout=10)
            results[i] = (i, fn(i), None)
        except BaseException as exc:  # keep thread failures visible
            results[i] = (i, None, exc)
        finally:
            connections.close_all()   # close this thread's DB connection

    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(worker, range(n)))
    return results
```

For HTTP-level races, use `LiveServerTestCase` with token authentication and one `httpx`/`requests` client per thread, or a separate `APIClient` per thread. Do not use one shared client if the client stores mutable state.

---

## 4. C1: no double spending under concurrent retries

### 4.1 Oracle

For one logical transfer with key `K`:

- Exactly **one** `Transfer` row exists for `K`.
- Exactly **one** debit movement and **one** credit movement exist for that transfer (plus any fee movement, if fees are in scope).
- The source balance decreased by exactly the amount once; the destination increased by exactly the amount once.
- Every HTTP response for a duplicate is either the original success (same transfer ID and body) or the contract's duplicate conflict error. It must not be a new success with a new transfer ID.
- Total money in the system is unchanged (except explicit fee accounts, which must be accounted for).
- A duplicate attempt did not create a second outbox event, a second "transfer succeeded" audit event, or a second ledger pair.

For distinct keys racing for the same funds, the oracle is the C2 invariant plus ledger consistency; see C2-06/C2-07.

### 4.2 Required C1 tests

| ID | Test name | Attack | Expected result / assertion |
|---|---|---|---|
| **C1-01** | `test_C1_sequential_replay_same_key_commits_once` | POST transfer with key `K`; after success, send the identical body with `K` again. | One transfer only. First response success; second returns the stored result (same transfer ID) or an exact `idempotency_key_conflict`/duplicate contract code. Source and destination reflect exactly one move. Transfer count = 1; ledger count = 2 (or 1 transfer row + 2 legs); outbox count = 1. |
| **C1-02** | `test_C1_concurrent_same_key_commits_once` | N=8 threads, same principal, same key `K`, same amount/destination, released by one barrier. | Exactly one transfer and one debit/credit pair. All successful responses reference the same transfer ID; at most one is "created"; the rest are replay or in-flight conflict. No 5xx. Repeat 100 iterations with a fresh key/account each time. |
| **C1-03** | `test_C1_commit_then_lost_response_retry` | Commit the transfer, then raise a connection-reset/timeout before the response reaches the client; retry the same key. | The first attempt left exactly one committed transfer. The retry returns the stored result; balance still reflects one move; no second transfer/ledger pair. This is the critical "server succeeded, client did not hear" case. |
| **C1-03b** | `test_C1_process_crash_after_commit_retry` | Child process commits, then `os._exit(1)` before acknowledging; restart and retry the same key. | Same as C1-03. If this is not automated, record it as a manual integration check and do not count it as covered. |
| **C1-04** | `test_C1_rollback_before_commit_retry` | Inject an exception after the debit leg and before the credit leg, inside the atomic block; first request fails; retry the same key. | First attempt leaves zero financial rows and unchanged balances. Retry succeeds exactly once. There is no orphaned "in progress" idempotency row and no half-applied transfer. |
| **C1-05** | `test_C1_same_key_different_payload_conflict` | Use key `K` for amount 10 to destination A; replay `K` with amount 999 or destination B. | Exact `409 idempotency_key_conflict` (or the documented code). Original transfer unchanged; no second debit; balances unchanged. The key alone must not authorize a different payload. |
| **C1-06** | `test_C1_missing_key_retry_contract` | Send two identical transfers without an idempotency key. | If both succeed, C1 is **false** for clients that retry without a key; record it and either require the key or narrow the claim. If the API rejects the request, assert the exact field error and no side effects. A server-generated key that is not echoed on retry does not make an unkeyed retry safe. |
| **C1-07** | `test_C1_two_distinct_full_balance_transfers_one_wins` | Balance 100; two concurrent transfers of 100 to different destinations, distinct keys. | Exactly one succeeds; the other is `insufficient_funds`; source becomes 0; exactly one destination is credited 100 and the other stays 0; one ledger pair; no negative balance. Repeat 100 iterations. |
| **C1-08** | `test_C1_n_distinct_debits_do_not_overdraw` | Balance 100; ten concurrent transfers of 20 with distinct keys. | Exactly 5 succeed and 5 are refused; source 0; each success credited its destination exactly once; ledger count = 10 rows (5 pairs); total value conserved; no negative. Also run 6 x 20 (5 succeed, 1 refused) and 11 x 10 (10 succeed, 1 refused). |
| **C1-09** | `test_C1_opposite_direction_transfers_lock_order` | A=100, B=100; concurrently A->B 100 and B->A 100. | Both succeed with deterministic lock ordering, or a deadlock is retried exactly once; final A=100, B=100; exactly two transfers; no partial leg. No unhandled 500. |
| **C1-10** | `test_C1_duplicate_worker_delivery_commits_once` | Deliver the same queue message/task ID twice, concurrently or sequentially, to the transfer worker. | One debit, one credit, one transfer. The second delivery is acknowledged as already processed; no duplicate side effects. This is a different entry point from HTTP. |
| **C1-11** | `test_C1_retry_storm_does_not_drift` | 100 sequential replays of the same key plus 10 concurrent replays. | One transfer only; row counts do not grow per retry beyond one idempotency record; balances stable; no duplicate outbox/audit success events. |
| **C1-12** | `test_C1_idempotency_key_retention_covers_retry_window` | Advance the clock past the idempotency retention TTL and replay the same key. | Contract must say either (a) key retained for at least the maximum supported retry window, or (b) an expired key gets `409 idempotency_key_expired` and no debit. If the replay is accepted as a new transfer after the TTL, the claim is false beyond that TTL. |
| **C1-13** | `test_C1_idempotency_key_scoped_to_principal` | Principal A and principal B use the same key value. | No cross-user replay and no cross-account debit. Either independent keys or a non-leaking conflict; assert no balance change for the other principal and no data leak. |
| **C1-14** | `test_C1_transfer_to_self` | Transfer from an account to itself. | If allowed: one transfer, net zero, balanced ledger, no negative. If refused: exact error, no rows, no balance change. This catches double-entry mistakes. |
| **C1-15** | `test_C1_in_flight_duplicate_contract` | First request holds the lock/transaction open; a second request with the same key arrives while the first is in flight. | Second waits and returns the original result, or returns an exact `409 idempotency_in_progress`; exactly one financial effect. No 500 and no second transfer after the first commits. |
| **C1-17** | `test_C1_two_process_workers_commit_once` | Run the same key through two separate OS processes/worker processes against the same database. | One transfer only. This catches in-process `threading.Lock`/local-cache idempotency that passes the thread test but fails in production with multiple gunicorn/Celery workers. |

### 4.3 C1 assertions in concrete terms

```python
def test_C1_concurrent_same_key_commits_once(api, accounts):
    source, destination = accounts(balance="100.00", destination="0.00")
    key = "c1-02-fixed-key"
    before = snapshot(source, destination)

    results = run_concurrently(
        8,
        lambda i: api.post(
            "/api/transfers/",
            json={"from": source.pk, "to": destination.pk,
                  "amount": "10.00"},
            headers={"Idempotency-Key": key},
        ),
    )

    assert all(exc is None for _, _, exc in results), results
    responses = [r for _, r, _ in results]

    # Do not assert "exactly one HTTP 2xx": replay may legitimately return 200.
    # Assert one financial effect.
    assert Transfer.objects.filter(idempotency_key=key).count() == 1
    assert LedgerEntry.objects.filter(transfer__idempotency_key=key).count() == 2
    assert balance(source) == Decimal("90.00")
    assert balance(destination) == Decimal("10.00")

    transfer_ids = {r.json()["transfer_id"] for r in responses
                    if r.status_code in (200, 201)}
    assert len(transfer_ids) == 1
    assert all(r.status_code in (200, 201, 409) for r in responses)
    assert_no_second_effect(before, source, destination)
```

For the exact status code, freeze the API contract. Recommended contract: `201` for a new transfer, `200` for an idempotent replay, `409` for a conflict/in-flight duplicate. If the project uses a different code, assert that exact code and exact `error.code`; a bare `400` is not enough.

### 4.4 Retry/commit matrix to test

| First attempt | Retry | Expected |
|---|---|---|
| Committed; response lost | Same key | One transfer; retry returns original result. |
| Committed; client timeout | Same key | One transfer; retry returns original result. |
| Rolled back before commit | Same key | No rows from first attempt; retry may commit once. |
| Failed validation before service | Same key | No financial rows; retry's behavior follows the documented key policy. |
| In flight | Same key | Wait or exact in-flight conflict; one transfer eventually. |
| Committed | Same key, different payload | Conflict; original unchanged; no second debit. |
| Committed | Same key after TTL | Per contract: rejected as expired or duplicate; never a silent second debit. |
| Unknown / 5xx after request sent | Same key | Client must be able to retry safely; test the server, not just the client. |

---

## 5. C2: balance can never go negative

### 5.1 Oracle

After every operation, for every account:

- `balance >= 0` for the stored balance, and `available_balance >= 0` if holds/reserves exist.
- `balance == opening_balance + sum(credits) - sum(debits)` for the account's ledger movements.
- Every committed transfer has exactly one debit leg and one credit leg (plus explicit fee legs), and the legs sum to zero.
- A refused transfer changed **none** of: balances, transfer rows, ledger rows, outbox events, idempotency success state, or a cached balance.
- No partial transfer exists: a debit without its matching credit is a rollback bug even if both balances happen to be nonnegative.
- The database rejects a negative balance even if the application check is removed or bypassed.

### 5.2 Boundary matrix

Use currency minor units or exactly two decimal places. Choose one and encode it in the tests.

| Balance | Amount | Fee | Expected |
|---|---:|---:|---|
| 100.00 | 99.99 | 0.00 | Success; source 0.01. |
| 100.00 | 100.00 | 0.00 | Success; source 0.00. This proves the comparison is inclusive. |
| 100.00 | 100.01 | 0.00 | Refused; source 100.00; no rows. This is the one-past case. |
| 100.00 | 99.99 | 0.02 | Refused; effective debit 100.01; source 100.00; no fee charged. |
| 100.00 | 99.98 | 0.02 | Success; source 0.00. |
| 0.00 | 0.01 | 0.00 | Refused; no rows. |
| 0.00 | 0.00 | 0.00 | Per contract: reject `amount_must_be_positive`; no rows. |
| 100.00 | -0.01 | 0.00 | Refused; source must not be credited. |
| 100.00 | 10**30 | 0.00 | Refused as insufficient; no overflow/500. |
| 100.00 | `0.001` | 0.00 | Per currency scale: reject or round explicitly; must not bypass the check. |
| 100.00 | `NaN` / `Infinity` | 0.00 | Rejected before comparison; no 500. |
| 100.00 | `None` / `"abc"` / `{}` | 0.00 | Rejected with field error; no rows. |
| 100.00 | 100.00 | 0.00, currency mismatch | Rejected unless conversion is explicit and accounted for; no value creation. |

### 5.3 Required C2 tests

| ID | Test name | Attack | Expected result / assertion |
|---|---|---|---|
| **C2-01** | `test_C2_exact_balance_succeeds_to_zero` | Balance 100.00, transfer 100.00. | Success; source 0.00; destination +100.00; ledger balanced; no negative. This is the positive boundary that proves the rule is not off by one in the strict direction. |
| **C2-02** | `test_C2_one_minor_unit_past_balance_refused_no_side_effects` | Balance 100.00, transfer 100.01. Repeat from balance 0 with 0.01 and balance 1.00 with 1.01. | Exact refusal (`409 insufficient_funds` or the documented business error), not a generic 400/500. Balances unchanged; transfer/ledger/outbox counts unchanged; no `in_progress` idempotency row left behind. |
| **C2-03** | `test_C2_negative_amount_cannot_credit_source` | Amount -10.00. | Refused (`400/422 amount_must_be_positive`); source unchanged; destination unchanged; no ledger row. A sign bug here would let an attacker mint money. |
| **C2-04** | `test_C2_zero_amount_contract` | Amount 0.00. | Per contract: reject `amount_must_be_positive`; no transfer, no ledger, no fee. Do not allow a no-op transfer that pollutes the ledger. |
| **C2-05** | `test_C2_amount_classes_rejected_without_writes` | Parameterize: `0.001`, `100.005`, `Decimal("NaN")`, `Decimal("Infinity")`, `"10"`, `None`, `10.0` (float), `10**30`, missing amount, extra unknown field. | Each class asserted separately with the exact field error. No balance change, no rows. Reject as close to the edge as possible; do not rely on a random sample. |
| **C2-06** | `test_C2_two_concurrent_full_balance_transfers_one_wins` | Balance 100; two concurrent 100 transfers to different destinations, distinct keys. | Exactly one success, one insufficient-funds refusal; source 0; one destination credited, the other 0; one ledger pair; no negative. Repeat 100 iterations. |
| **C2-07** | `test_C2_concurrent_debits_at_aggregate_boundary` | Balance 100; 5 x 20 (must all succeed), 6 x 20 (5 succeed, 1 refused), 11 x 10 (10 succeed, 1 refused). | Final source 0 in all three; success count exactly capacity; every success has a matching credit; no negative; total value conserved. |
| **C2-08** | `test_C2_refusal_snapshot_is_identical` | Parameterized over every refusal in C2-02..C2-05 and C2-13. | A shared `snapshot()` helper proves balances, Transfer count, Ledger count/sum, Outbox count, and cached balance are unchanged. This is the "world did not change" assertion, not just a status-code check. |
| **C2-09** | `test_C2_database_check_constraint_blocks_direct_update` | Bypass the service: `Account.objects.filter(pk=...).update(balance=F("balance") - 20)` from balance 10, or raw SQL `UPDATE ... SET balance = -1`. | `django.db.utils.IntegrityError` (PostgreSQL `CheckViolation`) naming the `balance >= 0` constraint; row remains 10. This proves the **database** layer refuses, not the application. If no constraint exists, this test fails and the "never" claim is false for direct writers. |
| **C2-10** | `test_C2_application_guard_refuses_before_write` | Call the service with insufficient funds; capture SQL and service exception. | Custom `InsufficientFunds`/`ValidationError` with exact code, not `IntegrityError`. Assert no `UPDATE`/`INSERT` against accounts or ledger was executed, or that the DB constraint was not the thing that fired. If the only guard is the DB, classify it as platform refusal and say so. |
| **C2-11** | `test_C2_direct_orm_and_admin_cannot_bypass` | Call `account.balance = -1; account.save()`, admin form/action, management command, bulk `update()`, and management/import path. | Each path either refuses or is blocked by the DB constraint. If one path succeeds, the claim is limited to the HTTP endpoint; record it and add the guard or scope the claim. |
| **C2-12** | `test_C2_rollback_mid_transfer_keeps_ledger_consistent` | Patch the credit leg (or outbox insert) to raise after the debit leg was written inside `atomic()`. | Both balances unchanged; zero Transfer rows; zero Ledger rows; no outbox event; exception propagated. Then retry the same key and assert exactly one successful transfer. |
| **C2-13** | `test_C2_fee_cannot_push_balance_negative` | Balance 100, amount 99.99, fee 0.02; and boundary amount 99.98/fee 0.02. | 99.99+0.02 refused with no fee and no rows; 99.98+0.02 succeeds to zero. A balance check that ignores fees fails this test. |
| **C2-14** | `test_C2_property_random_transfer_sequences` | Hypothesis state machine: 3 accounts, random amounts including exact balance and one past, random keys, sequential operations; then a concurrent variant with random distinct keys. | After every operation: all balances >= 0; total value conserved; ledger sum matches each balance; no orphan transfer; accepted transfers appear exactly once; refusals leave snapshots unchanged. Record the failing seed and keep it as a regression test. |
| **C2-15** | `test_C2_ledger_balance_invariant_after_every_operation` | Helper used by all tests: per account `balance == opening + credits - debits`; every transfer has two legs summing to zero (plus explicit fee legs). | Invariant holds after success, refusal, rollback, replay, and concurrent runs. This is the data-invariant claim; a balance that is merely clamped or cached is not enough. |
| **C2-16** | `test_C2_migration_backfill_cannot_create_negative` | Load legacy fixtures at zero/one-past boundaries, run migrations/backfill, then run C2-01/C2-02/C2-06 on the migrated DB. | No negative balance after migration; backfill is idempotent if rerun; ledger and balances agree. A green release note on an unmigrated test DB is not evidence. |
| **C2-17** | `test_C2_holds_and_available_balance` (only if holds exist) | Place a hold, then race a transfer that would consume held funds; also create a hold at the boundary. | `available_balance >= 0`; held funds are not spendable twice; ledger and hold accounting reconcile. If holds exist but are not modeled, the claim "balance" is ambiguous and must be scoped. |
| **C2-18** | `test_C2_reversal_refund_adjustment_cannot_overdraw` | Attempt reversal/refund/admin adjustment that would debit an account below zero (or reverse a credit already spent). | Refused or represented as a compensating ledger entry that never makes the stored balance negative; exact code/layer; snapshot unchanged on refusal. |

### 5.4 The side-effect snapshot every refusal test must use

```python
def snapshot(*accounts):
    return {
        "balances": {a.pk: Account.objects.get(pk=a.pk).balance for a in accounts},
        "transfer_count": Transfer.objects.count(),
        "ledger_count": LedgerEntry.objects.count(),
        "ledger_sum": LedgerEntry.objects.aggregate(total=Sum("amount"))["total"] or 0,
        "outbox_count": OutboxEvent.objects.count(),
        # If balances are cached, include the cache read here too.
    }


def assert_no_money_moved(before, after):
    assert after["balances"] == before["balances"]
    assert after["transfer_count"] == before["transfer_count"]
    assert after["ledger_count"] == before["ledger_count"]
    assert after["ledger_sum"] == before["ledger_sum"]
    assert after["outbox_count"] == before["outbox_count"]
```

Use a fresh DB connection for `after` when the refusal happened in another thread/process. Audit logging is a separate channel: a refusal **should** usually leave an audit/log record, but that record must not be a financial row. If audit rows are written inside the same transaction, they disappear on rollback; test the separate log channel too (stdout/file/syslog) so refusals are still observable.

---

## 6. Refusal classification: assert who refused

Never write `with pytest.raises(Exception)` or `assert response.status_code == 400` and call it coverage. For every refusal, record the `(HTTP status, error code, reason, layer)` tuple.

Freeze a contract like this (replace with the project's actual contract, but do not leave it implicit):

| Condition | HTTP | `error.code` | Refusing layer |
|---|---:|---|---|
| Malformed JSON / missing field / wrong type | 400 or 422 | `validation_error` + field | Serializer/view |
| `amount <= 0` | 400 or 422 | `amount_must_be_positive` | Service/validator |
| `amount + fee > available balance` | 409 | `insufficient_funds` | Service (application) |
| Same key, same payload, already committed | 200/201 | original result | Idempotency layer |
| Same key, different payload | 409 | `idempotency_key_conflict` | Idempotency layer |
| Same key, first request still in flight | 409 | `idempotency_in_progress` | Idempotency layer |
| Key expired beyond retention | 409 | `idempotency_key_expired` | Idempotency layer |
| Deadlock / serialization failure | 409 or 503, retryable | `retryable_conflict` | Database/driver |
| DB check constraint fired unexpectedly | 409 (mapped), never 500 | `insufficient_funds` | Database constraint (defense in depth) |

Classification rules:

1. **Application refusal** is proven by a custom exception/error code and by the absence of a DB constraint error. At the HTTP layer, assert the exact code and check the log/exception cause; do not accept a generic `IntegrityError` that happens to map to the same response.
2. **Database refusal** is proven by calling the ORM/raw SQL directly and catching `IntegrityError` with the constraint name. If the application's own guard was bypassed, the DB is the only thing protecting the claim; say so in the evidence.
3. **Platform/driver refusal** (deadlock, serialization, connection loss) is not proof that the business rule ran. Assert that no partial write occurred, classify it as retryable, and retry exactly once in the test; never count it as the rule's negative.
4. **Serializer refusal** (400 before the service) proves only input validation. It does not prove the balance rule; use a service spy or query counter to assert the service was never called, or test the service directly.
5. If the app catches `Exception` and returns 400, add a test that would fail on a wrong layer. Otherwise a real `IntegrityError`/bug becomes an indistinguishable "bad request."

```python
def test_C2_one_cent_past_balance_is_refused_by_the_application(api, accounts):
    source, destination = accounts(balance="100.00", destination="0.00")
    before = snapshot(source, destination)

    response = api.post(
        "/api/transfers/",
        json={"from": source.pk, "to": destination.pk, "amount": "100.01"},
        headers={"Idempotency-Key": "c2-02"},
    )

    assert response.status_code == 409          # freeze the contract
    assert response.json()["code"] == "insufficient_funds"
    assert_no_money_moved(before, snapshot(source, destination))


def test_C2_database_constraint_is_a_real_second_line(accounts):
    source, _ = accounts(balance="10.00", destination="0.00")

    with pytest.raises(IntegrityError) as excinfo:
        Account.objects.filter(pk=source.pk).update(
            balance=F("balance") - Decimal("20.00")
        )

    assert "account_balance_nonnegative" in str(excinfo.value)
    assert Account.objects.get(pk=source.pk).balance == Decimal("10.00")
```

The second test is not optional if the claim says "can never go negative." Without a DB constraint, the honest claim is "the HTTP endpoint refuses overdrafts," not "the balance can never go negative."

---

## 7. Entry-point matrix: one invariant, every write path

Run the C2 one-past test and the C1 replay test through every path that can create or modify a balance.

| Entry point | How to exercise it | Tests to run | If it bypasses the guard |
|---|---|---|---|
| HTTP API | `POST /api/transfers/` with auth | C1-01..C1-15, C2-02..C2-08 | This is the nominal path; still not the whole claim. |
| Service/use-case function | Direct call to `transfer_money(...)` | C1-02, C1-04, C2-02, C2-10, C2-12 | A view-level check that is not in the service is bypassed by every internal caller. |
| Django admin | Admin action/form save | C2-02, C2-11 | Admin is a classic direct-`save()` bypass. |
| Management command | `manage.py transfer` / `adjust_balance` | C2-02, C2-11 | Commands often skip serializer validation. |
| Celery/queue worker | Deliver the same task/message twice | C1-10, C1-02, C2-02 | Queue redelivery is the real retry path. |
| Bulk import / ETL | `bulk_create` / `QuerySet.update` | C2-09, C2-11, C2-16 | Bulk paths often bypass per-object checks and signals. |
| Reversal / refund / chargeback | Run the compensating operation | C2-18, C2-15 | A reversal can push a spent account below zero if not capped. |
| Reconciliation / backfill | Scheduled job / data migration | C2-14, C2-16 | A recompute can overwrite a correct balance or create a negative one. |
| Direct ORM | `account.balance = -1; account.save()` | C2-09, C2-11 | Only a DB constraint stops this. |
| Raw SQL / migration | `UPDATE accounts SET balance = -1` | C2-09 | Outside the app; needs DB-level enforcement to be in scope. |
| Restore/replica | Restore a backup or read from a lagging replica | Not covered by these tests | If reads come from a replica, stale balance can bypass the check; record as residual risk or add a read-your-writes test. |

If only the HTTP row is tested, the claim must be written as "the HTTP transfer endpoint rejects overdrafts." That is a much weaker claim than "balance can never go negative."

---

## 8. Verify the verifier: mutation tests

For each mechanism, remove or weaken it and confirm the named test fails. A test that passes after the guard is removed is testing nothing.

| Mutation | Test that must fail | What it proves |
|---|---|---|
| Remove the unique constraint on `(principal, idempotency_key)`, keep a check-then-insert `get_or_create`. | C1-02 | The concurrent duplicate test actually exercises the race, not just the happy path. |
| Remove the idempotency lookup entirely. | C1-01, C1-03 | Replay/retry tests detect a second debit. |
| Replace the atomic conditional `UPDATE ... WHERE balance >= amount` with `account.balance -= amount; account.save()`. | C1-07, C2-06, C2-07 | The concurrency tests detect lost updates. |
| Remove `select_for_update()` or make it a no-op (SQLite or mocked). | C1-07, C1-09, C2-06 | Row locking is load-bearing; the test is not relying on serialization by accident. |
| Remove the application `amount <= balance` check. | C2-02 | The boundary/one-past test detects the missing guard. |
| Remove the DB `CHECK (balance >= 0)` constraint. | C2-09 | The direct-ORM test proves the DB is the second line, not just a decorative migration. |
| Remove `transaction.atomic` around the debit and credit. | C2-12, C2-15 | The rollback test detects a half-applied transfer. |
| Make the idempotency TTL zero or shorter than the retry window. | C1-12 | Retention is tested, not assumed. |
| Replace the balance check with `except Exception: return 400`. | Refusal-classification tests | The test fails on wrong code/layer; it does not accept "something failed." |
| Use a process-local lock/cache for idempotency. | C1-17 | Multi-process production behavior is covered. |
| Return success when an `IntegrityError` occurs. | C2-09, C2-08 | Fail-open handlers are caught. |

Record the mutation report as evidence: mutant name, command, result (`killed`/`survived`), and the test ID that killed it. A surviving mutant is a gap, not a nuisance.

---

## 9. Evidence package that justifies each claim

For each claim, the evidence file/PR comment must contain:

```text
Claim ID: C1 (or C2)
Claim text: exact scoped sentence, not "no double spending" in the abstract
Commit: <40-char SHA>
Test IDs and files: tests/negative/test_transfer_idempotency.py::...
Command: pytest -q <paths> --repeats=100   (or the project's runner)
Environment: PostgreSQL <version>, default_transaction_isolation=<...>,
             Django <version>, Python <version>, worker/thread count,
             process count, connection pool size
Result: <pass/fail counts per test; iteration counts; zero failures>
Artifacts: JUnit XML path, CI job URL, failure-injection log path,
           DB snapshot query output, mutation report path
Mutations killed: M1..M3 for C1; M4..M6 for C2
Residual risk / not covered: <explicit list>
Status: SUPPORTED (scope) or UNPROVEN / REFUTED
```

### Minimum evidence for C1

- C1-02 concurrent same-key test, 100 iterations, on PostgreSQL, with 8+ threads; zero duplicate transfers and zero duplicate ledger pairs.
- C1-03 commit-then-lost-response retry; C1-04 rollback-then-retry; C1-05 key/payload conflict.
- C1-17 multi-process duplicate test.
- Unique constraint on the idempotency key shown in the schema/migration; the idempotency row and financial rows committed in one transaction.
- Mutation M1 (remove unique constraint) and M2 (remove idempotency lookup) both kill the tests.
- C1-12 retention evidence covering the documented retry window.

This supports a claim such as: "Within PostgreSQL 16 at READ COMMITTED and the tested process/worker topology, requests carrying an idempotency key retained for 24 hours commit at most one transfer per key." It does **not** support an unqualified "no double spending" claim for clients that omit the key, use a different key on retry, or retry after 24 hours.

### Minimum evidence for C2

- C2-01 exact balance to zero; C2-02 one minor unit past; C2-08 side-effect snapshot unchanged after every refusal.
- C2-06/C2-07 concurrent distinct debits at and one past aggregate capacity; C2-12 rollback midway.
- C2-09 direct ORM/raw-SQL attempt blocked by a named DB `CHECK` constraint.
- C2-11/C2-18 entry points: admin, command, bulk, worker, reversal.
- C2-14 property run plus C2-15 ledger invariant after every operation.
- Mutation M4 (remove app check) and M5 (remove DB constraint) both kill the relevant tests.
- Migration/backfill rerun on legacy data (C2-16).

This supports: "Within the tested application entry points and with the `accounts_balance_nonnegative` constraint installed, no operation can commit a negative balance; direct SQL by a superuser is outside this scope." It does not support "balance can never go negative" if a raw-SQL/superuser path, a missing constraint, or an untested writer exists.

### What is explicitly not evidence

- A green happy-path test.
- A 400 response with no error code, reason, or layer assertion.
- A test that expects any exception.
- A concurrency test on SQLite, or one that starts threads without a barrier.
- A test that passes after the guard is deleted.
- One successful iteration of a race test.
- A test that retries until green.
- A claim in the README with no row in the claim ledger.

---

## 10. What remains unproven after this plan passes

Be explicit in the release record. Even a fully green run of the above does not prove the absolute words in the original claims.

- **Formal guarantee.** Thread tests are probabilistic; 100 green iterations reduce the chance of a race but do not prove its absence. For an absolute claim, add a formal model (TLA+/Alloy) or a deterministic fault-injection campaign at every commit point.
- **Topology.** A single-process thread test does not cover multiple gunicorn workers, multiple hosts, connection pools with stale connections, or a load balancer retry.
- **Database/platform matrix.** Results are only for the tested PostgreSQL version and isolation level. SQLite, MySQL, and a different isolation level are untested unless run.
- **Crash timing.** A process kill at every instruction between debit and credit, during fsync, during failover, and after commit before ack is not exhaustively covered. The failpoint tests cover named points, not all points.
- **Retry window and key discipline.** If the client drops the key, generates a new key per retry, or retries after the retention TTL, C1 does not apply. If the server generates the key but does not echo/require it, retries are new transfers.
- **Other value paths.** Fees, holds/reserves, currency conversion, refunds/chargebacks, interest, reconciliation, admin adjustments, bulk imports, and manual SQL may each have their own rules. Only tested paths are covered.
- **Data already in the database.** Pre-existing negative balances, corrupted ledgers, or a migration that widens a constraint are not fixed by endpoint tests. C2-16 covers the tested migration, not every historical state.
- **Superuser / DBA / backup restore.** A DB constraint may be dropped or disabled; a restore may reintroduce old data. State whether these are in the threat model.
- **Cached/denormalized balances.** If `balance` is cached or updated asynchronously, a test against the cache and the ledger is needed; otherwise a stale cache can serve a negative available balance.
- **Read replicas.** A stale read can pass a balance check that a primary would reject. Not covered unless explicitly tested.
- **Audit evidence.** If audit rows live inside the failing transaction, evidence of refusals is lost on rollback. The separate log channel must be tested; otherwise incident investigation cannot tell what happened.

Use claim language with scope, for example:

> "On PostgreSQL 16 at READ COMMITTED, for the HTTP transfer endpoint and the tested worker topology, a request retried with the same idempotency key within 24 hours commits at most one transfer (C1-01..C1-17, 100 iterations). The database additionally enforces `balance >= 0`; direct superuser SQL and untested entry points are outside this claim."

Do not write: "No double spending. Balance can never go negative." That is an unqualified claim the tests cannot support.

---

## 11. Implementation and release gate

### P0 — blocking; do not make either claim without these

1. `C1-01` sequential replay.
2. `C1-02` concurrent same-key duplicate.
3. `C1-03` commit-then-lost-response retry.
4. `C1-05` same-key/different-payload conflict.
5. `C1-07` two full-balance transfers, one wins.
6. `C2-01` exact balance to zero.
7. `C2-02` one minor unit past, with side-effect snapshot.
8. `C2-06`/`C2-07` concurrent aggregate boundary.
9. `C2-09` direct ORM/raw SQL blocked by a named DB constraint.
10. `C2-12` rollback midway leaves no partial transfer.
11. Mutation M1, M2, M4, M5 killed.
12. Run everything on PostgreSQL with `transaction=True`; record version/isolation.

### P1 — required for the full claim

- `C1-04` rollback-then-retry; `C1-10` duplicate worker delivery; `C1-12` TTL; `C1-17` multi-process.
- `C2-08` shared side-effect snapshot across all refusals; `C2-11` entry-point matrix; `C2-13` fees; `C2-14` property test; `C2-15` ledger invariant; `C2-16` migration.
- Mutation M3 (lock removal), M6 (atomic removal), M7 (broad exception mapping).
- C2-03/C2-04/C2-05 amount classes.

### P2 — adjacent claims and residual-risk reduction

- C1-13 key scope, C1-14 self-transfer, C1-15 in-flight duplicate.
- C2-17 holds, C2-18 reversal/refund, currency conversion.
- Read-replica/read-your-writes test; audit-channel test; backup/restore test; failover test.

### Release decision

- If any P0 test fails: the corresponding claim is **REFUTED**; block the release or change the product behavior. Do not weaken the test.
- If a P0 test is skipped because CI lacks PostgreSQL: the claim is **UNPROVEN**; record the skip and do not advertise the claim.
- If the DB constraint is missing: C2 is at most "application endpoint refuses overdrafts," not "balance can never go negative."
- If idempotency is missing or the key is optional: C1 is at most "safe retries when the client cooperates," not "no double spending under concurrent retries."
- Update the claim ledger with exact scope, test IDs, date, commit, and residual risks. Negative results and open gaps stay visible; do not delete them when the happy path is green.

---

## Appendix: test ID index

| ID | Claim | One-line purpose |
|---|---|---|
| C1-01 | C1 | Sequential replay with same key debits once |
| C1-02 | C1 | Concurrent same-key requests commit once |
| C1-03 | C1 | Commit then lost response; retry does not double debit |
| C1-03b | C1 | Process crash after commit; retry does not double debit |
| C1-04 | C1 | Rollback before commit; retry succeeds once, no orphan key |
| C1-05 | C1 | Same key with different payload conflicts; original untouched |
| C1-06 | C1 | Missing key retry contract is explicit |
| C1-07 | C1/C2 | Two distinct full-balance transfers: one wins |
| C1-08 | C1/C2 | N concurrent distinct debits do not overdraw |
| C1-09 | C1/C2 | Opposite-direction transfers have a lock order / safe retry |
| C1-10 | C1 | Duplicate queue delivery commits once |
| C1-11 | C1 | Retry storm does not drift balances or rows |
| C1-12 | C1 | Key retention covers the retry window |
| C1-13 | C1 | Key is scoped to the principal; no cross-user replay |
| C1-14 | C1 | Self-transfer has a defined, balanced outcome |
| C1-15 | C1 | In-flight duplicate has a defined outcome |
| C1-17 | C1 | Two OS processes cannot both commit the same key |
| C2-01 | C2 | Exact balance succeeds to zero |
| C2-02 | C2 | One minor unit past is refused with no side effects |
| C2-03 | C2 | Negative amount cannot credit the source |
| C2-04 | C2 | Zero amount contract is explicit |
| C2-05 | C2 | Amount classes rejected individually, no writes |
| C2-06 | C2 | Two concurrent full-balance transfers: one wins |
| C2-07 | C2 | Concurrent debits at and past aggregate capacity |
| C2-08 | C2 | Refusal leaves the world unchanged |
| C2-09 | C2 | DB check constraint blocks direct ORM/raw SQL |
| C2-10 | C2 | Application guard refuses before any write |
| C2-11 | C2 | Alt entry points cannot bypass the guard |
| C2-12 | C2 | Rollback midway leaves no partial transfer |
| C2-13 | C2 | Fees cannot push the balance negative |
| C2-14 | C2 | Property/fuzz sequences preserve nonnegative balances |
| C2-15 | C2 | Ledger and balances agree after every operation |
| C2-16 | C2 | Migration/backfill does not create negative balances |
| C2-17 | C2 | Holds cannot be spent twice (if holds exist) |
| C2-18 | C2 | Reversal/refund/adjustment cannot overdraw |
