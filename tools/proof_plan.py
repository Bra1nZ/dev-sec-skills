#!/usr/bin/env python3
"""Plan proof re-runs for a diff: event-driven `proven`, not every PR (V2-29).

A `proven` claim is a statement about specific bytes: the model, the encoding,
the checker wrapper and the code the model abstracts. Re-running every proof on
every pull request is how a team stops running proofs at all; running none is
how a proof quietly describes code that no longer exists. This tool reads a
manifest that declares each proof's dependencies, compares a git range against
them, and answers three questions:

  - which proofs must be re-run for this diff;
  - which proofs the diff cannot have invalidated (their record already covers
    the last change to any dependency);
  - which changed proof material no proof declares (`unmapped`), which is a gap
    in the manifest rather than a quiet pass.

The manifest, not the tool, is the claim's scope. A dependency that nobody
declared is invisible here; `--require-complete` only catches changed files
that look like proof material (model, config, proof-script extensions) and are
not claimed by any entry. It cannot catch a shared helper that a proof uses
indirectly and the manifest omits. An unknown key is an input error, not a
silently ignored field: a typo in `depends_on` would otherwise delete the only
trigger and the proof would never re-run.

Freshness is a timestamp comparison, not a proof: a record whose
`finished_at` is at or after the last commit that touched a dependency is
treated as covering that change. A record with `status != completed` never
covers anything. This tool does not re-verify the record's hash or the tool's
semantics; `claim_lint` does the former, nothing does the latter.

Exit codes: 0 plan produced, 1 a gate failed (`--require-fresh` finds a proof
that must be re-run, or `--require-complete` finds unclaimed proof material),
2 tool, git, manifest or reference error.

Usage:
    python3 tools/proof_plan.py \
        --repo ../rbac_pg --base origin/main --head HEAD \
        --manifest spec/proofs/manifest.yaml \
        --manifest-base /tmp/opencode/manifest-base.yaml \
        --require-fresh --require-complete --json /tmp/opencode/proof-plan.json

`--base` should be the merge base of the PR, not the base branch tip; the
caller resolves it (`git merge-base origin/main HEAD`). The tool compares
`base..head`, reads the target repository and never modifies it.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

ID_RE = re.compile(r"^P-[0-9]{2,}$")
CLAIM_RE = re.compile(r"^C-[0-9]{2,}$")
# Files that look like proof material. A changed file with one of these
# extensions that no manifest entry claims is reported as unmapped.
MATERIAL_EXTENSIONS = (".tla", ".cfg", ".smt2", ".als", ".thy", ".lean",
                       ".dfy", ".agda", ".idr", ".p", ".v", ".sml")
RECORD_STATUSES = ("completed", "unverified", "failed", "error")


def run_git(repo, argv):
    proc = subprocess.run(["git", "-C", repo] + argv, capture_output=True,
                          text=True)
    if proc.returncode != 0:
        raise RuntimeError("git %s failed: %s"
                           % (" ".join(argv), proc.stderr.strip()))
    return proc.stdout


def changed_files(repo, base, head):
    out = run_git(repo, ["diff", "--name-status", "--find-renames",
                         "%s..%s" % (base, head)])
    items = []
    for line in out.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            items.append({"status": status, "path": parts[2],
                          "old_path": parts[1]})
        elif len(parts) >= 2:
            items.append({"status": status, "path": parts[1]})
    return items


def last_change(repo, base, head, path):
    """Committer time of the newest commit in base..head that touched path."""
    out = run_git(repo, ["log", "-1", "--format=%ct",
                         "%s..%s" % (base, head), "--", path]).strip()
    return int(out) if out else None


def parse_iso(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def compile_glob(pattern):
    """Gitignore-like glob: `*` stays in one path segment, `**` crosses them."""
    p = pattern.strip().lstrip("./")
    out = []
    i = 0
    while i < len(p):
        if p.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif p.startswith("**", i):
            out.append(".*")
            i += 2
        elif p[i] == "*":
            out.append("[^/]*")
            i += 1
        elif p[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(p[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class ManifestError(Exception):
    pass


def load_manifest(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError as exc:
        raise ManifestError("cannot read manifest %s: %s" % (path, exc))
    except yaml.YAMLError as exc:
        raise ManifestError("manifest %s is not valid YAML: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ManifestError("manifest %s is not a mapping" % path)
    if data.get("version") != 1:
        raise ManifestError("manifest version must be 1")
    unknown_top = set(data) - {"version", "proofs"}
    if unknown_top:
        raise ManifestError("manifest has unknown top-level key(s): %s"
                            % ", ".join(sorted(unknown_top)))
    proofs = data.get("proofs")
    if not isinstance(proofs, list):
        raise ManifestError("manifest must carry a proofs list")
    allowed = {"id", "claim", "artifact", "tool_output", "depends_on", "model",
               "encoding", "tooling", "assumptions", "proven_commit",
               "proven_at", "owner", "note"}
    seen = set()
    for entry in proofs:
        if not isinstance(entry, dict):
            raise ManifestError("a proof entry is not a mapping")
        pid = entry.get("id")
        if not isinstance(pid, str) or not ID_RE.match(pid):
            raise ManifestError("proof id %r does not match ^P-[0-9]{2,}$" % pid)
        # Unknown keys are rejected, not ignored: a typo in `depends_on` would
        # otherwise delete the trigger and the proof would never re-run.
        unknown = set(entry) - allowed
        if unknown:
            raise ManifestError("%s: unknown key(s): %s; a typo in depends_on "
                                "would silently drop a trigger"
                                % (pid, ", ".join(sorted(unknown))))
        if pid in seen:
            raise ManifestError("duplicate proof id %s" % pid)
        seen.add(pid)
        claim = entry.get("claim")
        if not isinstance(claim, str) or not CLAIM_RE.match(claim):
            raise ManifestError("%s: claim %r does not match ^C-[0-9]{2,}$"
                                % (pid, claim))
        for field in ("artifact", "tool_output"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ManifestError("%s: %s must be a non-empty path"
                                    % (pid, field))
        depends = entry.get("depends_on")
        if not isinstance(depends, list) or not depends or \
                not all(isinstance(v, str) and v.strip() for v in depends):
            raise ManifestError("%s: depends_on must be a non-empty list of "
                                "paths or globs" % pid)
        for field in ("model", "encoding", "tooling"):
            value = entry.get(field)
            if value is not None and (not isinstance(value, list)
                                      or not all(isinstance(v, str)
                                                 and v.strip() for v in value)):
                raise ManifestError("%s: %s must be a list of paths or globs"
                                    % (pid, field))
        assumptions = entry.get("assumptions")
        if not isinstance(assumptions, list) or not assumptions or \
                not all(isinstance(v, str) and v.strip() for v in assumptions):
            raise ManifestError("%s: assumptions must be a non-empty list; a "
                                "proof without declared assumptions is an "
                                "overclaim" % pid)
    return data


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def globs(entry):
    out = [entry["artifact"]]
    for field in ("depends_on", "model", "encoding", "tooling"):
        out.extend(entry.get(field) or [])
    return out


def match(items, pattern):
    regex = compile_glob(pattern)
    hits = []
    for item in items:
        if regex.match(item["path"].lstrip("./")) or \
                (item.get("old_path") and
                 regex.match(item["old_path"].lstrip("./"))):
            hits.append(item)
    return hits


def read_record(repo, path):
    full = path if os.path.isabs(path) else os.path.join(repo, path)
    try:
        with open(full, encoding="utf-8") as f:
            return json.load(f)
    except OSError as exc:
        raise ManifestError("cannot read tool_output %s: %s" % (path, exc))
    except ValueError as exc:
        raise ManifestError("tool_output %s is not JSON: %s" % (path, exc))


def plan(args):
    current = load_manifest(args.manifest)
    previous = (load_manifest(args.manifest_base) if args.manifest_base else None)
    previous_by_id = {e["id"]: e for e in (previous or {}).get("proofs") or []}
    current_ids = {e["id"] for e in current["proofs"]}

    files = changed_files(args.repo, args.base, args.head)
    results = []
    removed = []
    mapped_paths = set()

    for entry in current["proofs"]:
        pid = entry["id"]
        record = read_record(args.repo, entry["tool_output"])
        artifact_full = (entry["artifact"] if os.path.isabs(entry["artifact"])
                         else os.path.join(args.repo, entry["artifact"]))
        if not os.path.exists(artifact_full):
            raise ManifestError("%s: artifact not found: %s"
                                % (pid, entry["artifact"]))

        reasons = []
        hit_items = []
        for pattern in globs(entry):
            for item in match(files, pattern):
                if item not in hit_items:
                    hit_items.append(item)
                mapped_paths.add(item["path"].lstrip("./"))
                if item.get("old_path"):
                    mapped_paths.add(item["old_path"].lstrip("./"))
                reason = {"kind": "dependency-changed",
                          "path": item["path"],
                          "status": item["status"]}
                if reason not in reasons:
                    reasons.append(reason)
        if previous is not None:
            before = previous_by_id.get(pid)
            if before is None:
                reasons.append({"kind": "proof-added", "path": args.manifest})
            elif canonical(before) != canonical(entry):
                reasons.append({"kind": "manifest-changed",
                                "path": args.manifest})

        last = None
        for item in hit_items:
            for path in filter(None, (item["path"], item.get("old_path"))):
                stamp = last_change(args.repo, args.base, args.head, path)
                if stamp is not None and (last is None or stamp > last):
                    last = stamp

        record_finished = parse_iso(record.get("finished_at"))
        record_status = record.get("status")
        status = "fresh"
        if args.all:
            status = "rerun"
            reasons.append({"kind": "all", "path": ""})
        elif record_status != "completed":
            # A record that did not complete proves nothing, whether or not the
            # diff touched a dependency. Checked before the reasons gate on
            # purpose: `unverified`/`failed`/missing status never becomes fresh.
            status = "rerun"
            reasons.append({"kind": "record-not-completed",
                            "path": entry["tool_output"]})
        elif reasons:
            only_manifest = all(r["kind"] in ("manifest-changed", "proof-added")
                                for r in reasons)
            if only_manifest:
                # The proof definition itself moved; the old record describes
                # the old definition, so it cannot cover the new one.
                status = "rerun"
            elif last is not None and record_finished is not None and \
                    record_finished >= datetime.fromtimestamp(last, timezone.utc):
                status = "fresh"
                reasons.append({"kind": "record-covers-change",
                                "path": entry["tool_output"]})
            else:
                status = "rerun"
                reasons.append({"kind": "record-predates-change",
                                "path": entry["tool_output"]})

        results.append({
            "id": pid,
            "claim": entry["claim"],
            "artifact": entry["artifact"],
            "tool_output": entry["tool_output"],
            "status": status,
            "record_status": record_status,
            "record_finished_at": record.get("finished_at"),
            "last_change": (datetime.fromtimestamp(last, timezone.utc)
                            .isoformat() if last is not None else None),
            "reasons": reasons,
        })

    for pid in sorted(set(previous_by_id) - current_ids):
        removed.append({"id": pid, "claim": previous_by_id[pid].get("claim")})

    unmapped = []
    for item in files:
        paths = [item["path"].lstrip("./")]
        if item.get("old_path"):
            paths.append(item["old_path"].lstrip("./"))
        if any(path in mapped_paths for path in paths):
            continue
        # A rename or delete counts too: a model that moved to a non-material
        # name still left the manifest, and only the old path shows it.
        if any(path.lower().endswith(MATERIAL_EXTENSIONS) for path in paths):
            unmapped.append({"path": paths[0], "status": item["status"]})

    return {
        "format": "dev-sec-skills/proof-plan/v1",
        "repo": args.repo,
        "base": args.base,
        "head": args.head,
        "changed_files": files,
        "proofs": results,
        "removed": removed,
        "unmapped_proof_material": unmapped,
        "summary": {
            "proofs": len(results),
            "fresh": sum(1 for r in results if r["status"] == "fresh"),
            "rerun": sum(1 for r in results if r["status"] == "rerun"),
            "removed": len(removed),
            "unmapped": len(unmapped),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True,
                    help="target git repository (read-only)")
    ap.add_argument("--base", required=True, help="merge base or base commit")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--manifest", required=True,
                    help="proof manifest (YAML, schemas/proof-manifest.schema.json)")
    ap.add_argument("--manifest-base", default=None,
                    help="previous manifest; an edited or added proof is re-run")
    ap.add_argument("--all", action="store_true",
                    help="re-run every proof, for a scheduled full run")
    ap.add_argument("--require-fresh", action="store_true",
                    help="exit 1 when a proof must be re-run")
    ap.add_argument("--require-complete", action="store_true",
                    help="exit 1 when changed proof material is declared by no entry")
    ap.add_argument("--json", default=None, help="write the plan as JSON")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.repo):
        print("error: repository not found: %s" % args.repo, file=sys.stderr)
        return 2
    for label, path in (("manifest", args.manifest),
                        ("manifest-base", args.manifest_base)):
        if path and not os.path.exists(path):
            print("error: %s not found: %s" % (label, path), file=sys.stderr)
            return 2

    try:
        result = plan(args)
    except (RuntimeError, ManifestError, KeyError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    for entry in result["proofs"]:
        if entry["status"] == "rerun":
            reason = entry["reasons"][-1] if entry["reasons"] else {}
            print("RERUN %-6s %-6s %-20s %s"
                  % (entry["id"], entry["claim"], reason.get("kind", ""),
                     reason.get("path", "")))
        else:
            print("FRESH %-6s %-6s %s"
                  % (entry["id"], entry["claim"], entry["artifact"]))
    if not result["proofs"]:
        print("PLAN  no proofs declared: the manifest is empty")
    for entry in result["removed"]:
        print("INFO  removed proof %s (%s)" % (entry["id"], entry["claim"]))
    for item in result["unmapped_proof_material"]:
        print("GAP   changed proof material maps to no entry: %s"
              % item["path"])
    print("plan: %d proof(s): %d rerun, %d fresh; %d removed; "
          "%d unmapped material; %d changed file(s)"
          % (result["summary"]["proofs"], result["summary"]["rerun"],
             result["summary"]["fresh"], result["summary"]["removed"],
             result["summary"]["unmapped"], len(result["changed_files"])))

    if args.json:
        parent = os.path.dirname(os.path.abspath(args.json))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")

    failed = False
    if not result["proofs"] and (args.require_fresh or args.require_complete):
        # An empty manifest makes --require-fresh vacuous. Say so instead of
        # letting a green gate look like proof coverage.
        print("note: no proofs are declared, so the gates below prove nothing "
              "about proof coverage")
    if args.require_fresh and result["summary"]["rerun"]:
        print("error: %d proof(s) must be re-run before the claim keeps "
              "`proven`" % result["summary"]["rerun"], file=sys.stderr)
        failed = True
    if args.require_complete and result["summary"]["unmapped"]:
        print("error: %d changed proof material file(s) are declared by no "
              "proof" % result["summary"]["unmapped"], file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
