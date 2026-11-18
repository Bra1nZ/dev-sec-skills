# codex-security LLM scans — evaluation note, not a channel record

Two repository-wide scans with `@openai/codex-security` 0.10.0 (bundling
codex-cli 0.167.1) over the pilots' clones, driven by the project's own model
hub instead of OpenAI. This note is a measurement of what the tool did on this
machine, in the same sense as `two-engine-2026-11-07.md`: it is not a
static-analysis channel record, does not go through
`schemas/static-analysis-run.schema.json`, carries no anchor, and routes no
finding to a cell. LLM findings are triage input, not evidence, and this note
exists so the inputs and the two workarounds they required survive `/tmp`
cleanup.

Disclosure note: the raw artifacts of scan 2 were briefly committed here and
were removed from the public repository — they contained source excerpts of a
private pilot, which violates this repository's own anchor discipline (a
finding's location is a path, a line range and a SHA-256, never the target's
source text). The full artifacts are available to the pilot's maintainers on
request; their SHA-256s are recorded below so any copy can be checked against
this note. Nothing else in this note quotes the pilots' source.

## Why this is not a static-analysis record

Three measured reasons, each sufficient on its own:

1. The runs are nondeterministic agent sessions; a repeat scan can report a
   different finding set, so the run→hash→triage contract of the channel has
   nothing stable to pin except the artifacts themselves.
2. `tools/sarif_evidence.py` rejects the output as designed: both real
   findings came back `UNMAPPED Codex Security … unknown-engine` because
   `spec/sarif/adapters.yaml` declares no `Codex Security` engine adapter.
   Adding one would be a separate decision; until then the findings cannot
   reach a cell, which is the fail-loud behavior working as intended.
3. The model was the project's own hub (`GLM-5.3` via vLLM 0.28.0 behind the
   hub's chat/completions API), not a fixed engine build.

## Environment

The hub speaks only chat/completions (`POST /responses` → 404), and codex-cli
0.167 refuses `wire_api = "chat"`. The bridge is a local LiteLLM 1.109.1 proxy
whose model entry is `openai/chat_completions/GLM-5.3` — that exact prefix
forces LiteLLM's Responses→chat-completions bridge. The codex profile used
for scans (a machine-local config file, its name not reproduced here) points
at `http://127.0.0.1:4000/v1` with `wire_api = "responses"`; its key comes
from an `auth.command` over a local file (codex 0.167 rejects `env_key`
combined with `auth`). The hub key exists only in the proxy process's
environment.

## Two host-specific workarounds (both undocumented surfaces)

Both were needed after the config above; both are re-check-on-upgrade items.

1. **The sandbox probe is unconditional.** codex-security always runs
   `codex sandbox -- codex --version` before a scan, and
   `sandbox_mode = "danger-full-access"` does not skip it (the scan runtime
   deletes `sandbox_mode` from its config by design — `scanRuntimeCodexConfig`
   in `dist/api.js`). Workaround: the SDK constructor accepts dependency
   injection, so the driver stubs the probe:

   ```js
   import { CodexSecurity, DEFAULT_DEPENDENCIES } from ".../@openai/codex-security/dist/api.js";
   const security = new CodexSecurity(
     { codexOverrides: { profile: "local", sandbox_mode: "danger-full-access" } }, // profile name is machine-local
     { ...DEFAULT_DEPENDENCIES, probeCodexSandbox: async () => {} },
   );
   ```

2. **bwrap cannot exec codex's own helper.** codex mounts
   `--perms 000 --tmpfs $CODEX_HOME --remount-ro $CODEX_HOME` to hide
   credentials, but its `codex-linux-sandbox` arg0 helper lives *inside*
   `CODEX_HOME`, so `execvp` inside the sandbox fails with `Permission denied`
   (measured: the same helper execs fine outside bwrap, and a plain
   `bwrap --ro-bind / /` execs it fine too). codex looks for bwrap on `PATH`
   before using its bundled candidate, so a PATH shim that forwards to the
   bundled `codex-resources/bwrap` lets sessions pass. The sandbox itself is
   not removed; only the broken exec path is avoided. Consequence: scan
   disposable clones in `/tmp`, never working copies with secrets.

The driver (~70 lines, `run()` with `maxTimeMinutes`, progress/warning
callbacks, JSON summary) and the shim live outside the repository at
`~/.config/codex-security/{scan-driver.mjs,shim-bin/bwrap}`; the driver text
is machine-specific only in the package path it imports.

## Scan 1: craft-i18n clone — 0 findings, and why that means little

| Field | Value |
| --- | --- |
| Target | clone of `craft-i18n` at `c812ee483a29f5123f1c52764a728a328050e016` |
| Mode / files | Standard, 411 tracked files |
| Wall clock | 1198 s |
| Outcome | `completed`, 0 reportable findings |
| Artifacts | lost with `/tmp`; sha256 recorded: report `ef4c46de…16b984`, SARIF `6517a271…4da3f2`, findings `58a04ffe…c1f70c5`, scanId `e3863c8e-cea3-4360-806c-c66a3e79bcf3` |

The zero is not evidence of absence. The pilot's own probe-backed gap C-08 was
present in the scanned tree: the catalog checker filters out control
characters and U+FEFF only, so other invisible/format characters pass — the
committed invisible-characters probe proves they reach a Row. The scan
reported nothing about it — not in findings, not in limitations, not in the
threat model. C-08 stays `open`; a clean LLM scan neither closes nor refutes a
claim with a runnable probe.

## Scan 2: rbac_pg clone — 2 findings, triaged against the pilot's own ledger

| Field | Value |
| --- | --- |
| Target | clone of `rbac_pg` at `d97860929b40a7a1f65e7b6a8cef66e72ef1cf4f` |
| Mode / files | Standard, 123 files; the scan itself states 21 were fully reviewed |
| Wall clock | 1115 s |
| Outcome | `completed`, 2 findings, both medium severity / high confidence |
| Artifacts | withheld from the public repository (source excerpts of a private pilot); SHA-256s: report `707b3a42…094ef`, SARIF `4cc0f917…2f9fb94`, findings `a4dd4b2b…65276`; scanId `479ee7d3-1291-4869-8f58-0af9222b3e5a` |

Triage against the pilot's own documents (this note records the dispositions
as review-queue input for the rbac_pg maintainers; nothing was routed to a
cell and nothing in `spec/pilots/rbac_pg/` was changed). The vectors are not
reproduced here — they name private source with exact locations; the summary
below is the level a public note may carry:

| Finding | Class | Disposition |
| --- | --- | --- |
| `rbac-auth-failure-forgery` (CWE-862/307) | an authentication bookkeeping operation is granted to untrusted application roles and can be driven against an arbitrary account | consistent with the pilot's declared DoS limitation (its own threat model, §4.12); the vector sharpens that section from generic DoS to targeted account lockout |
| `rbac-arbitrary-role-metadata-disclosure` (CWE-200) | an integration point added in v1.9 exposes access metadata for an arbitrary username to application roles | tension with the repository's own SECURITY.md: its post-D3 promise restricts metadata access to current-context getters, while the v1.9 grant permits an arbitrary-username query; the pilot's threat model declares metadata leakage a known limitation (§4.10), but this specific grant contradicts the D3 promise. Partially mitigated by role-membership filtering |

The second finding is the more valuable one: a doc-vs-code divergence inside
the pilot, surfaced by the tool. Both dispositions belong to the pilot's
maintainers; per the read-only pilot discipline nothing was fixed. The full
finding reports (dataflow, remediation, exact locations) travel to them
privately, outside this repository.

## Correction to the earlier local note

The 2026-11-17 local note said the codex-security SARIF lacks
`partialFingerprints`, based on the mock scan. The real scans disprove it:
every result carries `partialFingerprints["codexSecurity/v1"]` with a stable
SHA-256. The mock-mode observation was a mock artifact. Duplicate-detection
behavior on two *identical* findings is still untested; the two rbac findings
are distinct.

## What the two scans support, and what they do not

They support: the tool runs end-to-end on the project's own model hub through
a documented bridge; its reports carry source-backed evidence (citations,
dataflow, remediation) and an honest threat model with stated limitations;
its SARIF exercises the adapter gate's fail-loud path on an unknown engine.

They do not support: any coverage statement about the pilots' cells; any
closed or changed claim (C-08, C-13, the rbac_pg ledgers are untouched); the
completeness of either scan (one scan missed a probe-proven gap, and scan 2
reviewed 21 of 123 files). Neither scan was repeated, so nondeterminism was
not measured, only asserted from the tool's nature. Deep mode was not used.
