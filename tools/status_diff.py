#!/usr/bin/env python3
"""Status diff between two claim-ledger releases.

Compares claim IDs and status transitions between a base and a target
ledger. The gate rule: a claim may not escalate on the status ladder
(e.g. open -> tested) unless the target ledger adds evidence the base did
not have. Evidence identity is (kind, commit, artifact, command, tests,
date); a re-run with a newer date counts as new evidence.

Fail-closed base handling: a missing ref, a missing base ledger, or a base
ledger with no claims is an error. Pass --first-release to allow a repository
with no prior release; the escalation gate is then skipped explicitly.

Transitions:
  escalation  (rank up, e.g. open -> tested): error without new evidence
  downgrade   (rank down, e.g. tested -> open): warning, allowed but noted
  removed     (claim absent from the target): warning
  added       (new claim in the target): info

Exit codes: 0 no violations (warnings allowed), 1 violations found,
2 tool/usage error.

Modes:
  two files:  status_diff.py --base v1.yaml --target v2.yaml
  git ref:    status_diff.py --repo DIR --ledger docs/claims.yaml --git-ref v1.3

Usage:
    python3 tools/status_diff.py [--first-release] BASE TARGET
    python3 tools/status_diff.py --repo PATH --ledger REL --git-ref REF [--first-release]
"""

import argparse
import os
import subprocess
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# Status ladder, lowest to highest. "open" is below every evidence-backed
# status; "proven" is the top.
ORDER = {
    "open": 0,
    "reviewed": 1,
    "static-refinement": 2,
    "model-checked": 3,
    "tested": 4,
    "proven": 5,
}


def load_ledger_path(path):
    text = open(path, encoding="utf-8").read()
    return yaml.safe_load(text) or {}


def ref_exists(repo, ref):
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "%s^{commit}" % ref],
                       cwd=repo, capture_output=True)
    return r.returncode == 0


def load_ledger_ref(repo, ref, rel):
    """Load the ledger as it existed at a git ref; None if absent there.

    A ref that does not resolve raises LookupError: a typo, a missing tag, or
    a shallow clone must not silently disable the escalation gate.
    """
    if not ref_exists(repo, ref):
        raise LookupError("base ref not found: %s" % ref)
    r = subprocess.run(["git", "show", "%s:%s" % (ref, rel)],
                       cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return yaml.safe_load(r.stdout) or {}


def claims_of(ledger):
    claims = ledger.get("claims") if isinstance(ledger, dict) else None
    return {c["id"]: c for c in (claims or []) if isinstance(c, dict) and c.get("id")}


def evidence_keys(claim):
    """Canonical identity of each evidence entry."""
    keys = set()
    for ev in claim.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        keys.add((ev.get("kind"), ev.get("commit"), ev.get("artifact"),
                  ev.get("command"), tuple(sorted(ev.get("tests") or [])),
                  ev.get("date")))
    return keys


def main():
    ap = argparse.ArgumentParser(description="Claim-ledger status diff (dev-sec-skills)")
    ap.add_argument("base", nargs="?", help="base ledger (two-file mode)")
    ap.add_argument("target", nargs="?", help="target ledger (two-file mode)")
    ap.add_argument("--repo", help="repository root (git-ref mode)")
    ap.add_argument("--ledger", help="repo-relative ledger path (git-ref mode)")
    ap.add_argument("--git-ref", help="base git ref, e.g. a release tag (git-ref mode)")
    ap.add_argument("--first-release", action="store_true",
                    help="allow a missing base ref or ledger; the escalation gate is skipped")
    args = ap.parse_args()

    if args.git_ref:
        if not (args.repo and args.ledger):
            print("--git-ref requires --repo and --ledger", file=sys.stderr)
            return 2
        if not os.path.isfile(os.path.join(args.repo, args.ledger)):
            print("target ledger not found: %s" % os.path.join(args.repo, args.ledger),
                  file=sys.stderr)
            return 2
        try:
            base = load_ledger_ref(args.repo, args.git_ref, args.ledger)
        except LookupError as e:
            if args.first_release:
                print("status diff: %s; first release, gate skipped" % e)
                return 0
            print("status diff: %s" % e, file=sys.stderr)
            return 1
        if base is None:
            if args.first_release:
                print("status diff: no ledger at %s:%s; first release, gate skipped"
                      % (args.git_ref, args.ledger))
                return 0
            print("status diff: no ledger at %s:%s; set --first-release if this is "
                  "the first release" % (args.git_ref, args.ledger), file=sys.stderr)
            return 1
        try:
            target = load_ledger_path(os.path.join(args.repo, args.ledger))
        except (OSError, ValueError) as e:
            print("cannot read ledger: %s" % e, file=sys.stderr)
            return 2
        label = "%s@%s -> worktree" % (args.ledger, args.git_ref)
    elif args.base and args.target:
        try:
            base = load_ledger_path(args.base)
            target = load_ledger_path(args.target)
        except (OSError, ValueError) as e:
            print("cannot read ledger: %s" % e, file=sys.stderr)
            return 2
        label = "%s -> %s" % (args.base, args.target)
    else:
        print("use either BASE TARGET or --repo/--ledger/--git-ref", file=sys.stderr)
        return 2

    base_claims = claims_of(base)
    target_claims = claims_of(target)
    if not base_claims:
        if args.first_release:
            print("status diff: base ledger has no claims; first release, gate skipped (%s)"
                  % label)
            return 0
        print("status diff: base ledger has no resolvable claims; set --first-release "
              "if this is the first release (%s)" % label, file=sys.stderr)
        return 1

    errors, warnings, infos = [], [], []
    for cid in sorted(set(base_claims) | set(target_claims)):
        b, t = base_claims.get(cid), target_claims.get(cid)
        if b and not t:
            warnings.append("claim %s removed from the ledger" % cid)
            continue
        if t and not b:
            infos.append("claim %s added (status=%s)" % (cid, t.get("status")))
            continue
        bs, ts = b.get("status"), t.get("status")
        if bs == ts:
            continue
        brank, trank = ORDER.get(bs), ORDER.get(ts)
        if brank is None or trank is None:
            errors.append("claim %s: unknown status %r -> %r (ladder violation)"
                          % (cid, bs, ts))
        elif trank > brank:
            new_ev = evidence_keys(t) - evidence_keys(b)
            if new_ev:
                infos.append("claim %s: %s -> %s with %d new evidence entry(ies)"
                             % (cid, bs, ts, len(new_ev)))
            else:
                errors.append("claim %s: %s -> %s without new evidence"
                              % (cid, bs, ts))
        else:
            warnings.append("claim %s: %s -> %s (downgrade)" % (cid, bs, ts))

    print("status diff: %s | claims: %d base, %d target" % (label, len(base_claims), len(target_claims)))
    for sev, rows in (("error", errors), ("warning", warnings), ("info", infos)):
        for row in rows:
            print("  %-7s %s" % (sev, row))
    if not (errors or warnings or infos):
        print("  no status changes")
    print("total: %d error(s), %d warning(s), %d info" % (len(errors), len(warnings), len(infos)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
