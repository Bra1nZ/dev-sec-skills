#!/usr/bin/env python3
"""Adversarial eval runner for tools/claim_lint.py.

Each case in cases/*.yaml defines a synthetic project (files), an inline
ledger, and expectations: for each check L1..L5 either a severity that must
appear ("error" | "warning" | "info") or "none". `exit` is the expected
process exit code (0 clean/warnings allowed, 1 errors found).

A case may also declare `git.commits`: a list of `{message, files}` records
that are committed in order before the case files are written. Each commit's
SHA replaces `{{COMMIT_<n>}}` in later commit files, the ledger and the final
working tree, so a case can cite a real, resolvable commit whose artifact
bytes differ from the working tree. Without `git`, the temp root is not a
repository and the artifact-at-commit check reports nothing.

Fixtures are synthetic and marked as such in each file; they are not
evidence about any real project. A passing run means the linter's contract
holds on the adversarial cases, not that any production ledger is clean.

Usage:
    python3 evals/linter/run_evals.py [--cases DIR] [--claim-lint PATH]
"""

import argparse
import os
import re
import subprocess
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

FINDING_RE = re.compile(r"^\s*\[(L\d)\]\s+(error|warning|info)\b")


def run_case(case_path, claim_lint):
    """Run one case; return (name, problems, stdout)."""
    case = yaml.safe_load(open(case_path, encoding="utf-8"))
    name = case.get("name") or os.path.basename(case_path)
    problems = []
    with _temp_root(case) as (td, ledger_path):
        cmd = [sys.executable, claim_lint,
               "--root", td, "--suite-glob", case.get("suite_glob") or "**/*.py"]
        cmd += list(case.get("args") or [])
        cmd += [ledger_path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return name, ["claim_lint timed out"], ""
        found = {}
        for line in (r.stdout or "").splitlines():
            m = FINDING_RE.match(line)
            if m:
                found.setdefault(m.group(1), set()).add(m.group(2))
        for check, wanted in sorted((case.get("expect") or {}).items()):
            got = found.get(check, set())
            if wanted == "none":
                if got:
                    problems.append("%s: expected no findings, got %s"
                                    % (check, ",".join(sorted(got))))
            elif wanted not in got:
                problems.append("%s: expected %s, got %s"
                                % (check, wanted, ",".join(sorted(got)) or "no findings"))
        if "exit" in case and r.returncode != case["exit"]:
            problems.append("exit: expected %d, got %d" % (case["exit"], r.returncode))
    return name, problems, r.stdout or ""


def _subst(value, repl):
    """Replace {{COMMIT_n}} placeholders through a nested YAML structure."""
    if isinstance(value, str):
        for key, sub in repl.items():
            value = value.replace(key, sub)
        return value
    if isinstance(value, list):
        return [_subst(v, repl) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, repl) for k, v in value.items()}
    return value


def _write(td, rel, content):
    p = os.path.join(td, rel)
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


class _temp_root(object):
    """Temp project dir with the case files and the ledger written in.

    Optional `git.commits` are committed in order first; their SHAs are then
    substituted as {{COMMIT_n}} into later commit files, the case files and the
    ledger.
    """

    def __init__(self, case):
        self.case = case

    def _git(self, *args):
        return subprocess.run(["git"] + list(args), cwd=self.td,
                              capture_output=True, text=True, check=True)

    def __enter__(self):
        import tempfile
        self.td = tempfile.mkdtemp(prefix="l5-eval-")
        repl = {}
        spec = self.case.get("git") or {}
        if spec:
            self._git("init", "-q")
            self._git("config", "user.email", "eval@example.invalid")
            self._git("config", "user.name", "eval")
            for i, commit in enumerate(spec.get("commits") or []):
                for rel, content in (commit.get("files") or {}).items():
                    _write(self.td, rel, _subst(content, repl))
                self._git("add", "-A")
                self._git("commit", "-q", "--allow-empty", "-m",
                          commit.get("message") or "commit %d" % i)
                repl["{{COMMIT_%d}}" % i] = self._git(
                    "rev-parse", "HEAD").stdout.strip()
        for rel, content in (self.case.get("files") or {}).items():
            _write(self.td, rel, _subst(content, repl))
        self.ledger_path = os.path.join(self.td, "ledger.yaml")
        with open(self.ledger_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(_subst(self.case["ledger"], repl), f,
                           allow_unicode=True, sort_keys=False)
        return self.td, self.ledger_path

    def __exit__(self, *exc):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)
        return False


def main():
    ap = argparse.ArgumentParser(description="Adversarial evals for claim_lint")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--cases", default=os.path.join(here, "cases"))
    ap.add_argument("--claim-lint",
                    default=os.path.abspath(os.path.join(here, "..", "..", "tools", "claim_lint.py")))
    args = ap.parse_args()

    cases = sorted(f for f in os.listdir(args.cases) if f.endswith((".yaml", ".yml")))
    if not cases:
        print("no cases found in %s" % args.cases, file=sys.stderr)
        return 2

    passed, failed = 0, 0
    for fname in cases:
        name, problems, _ = run_case(os.path.join(args.cases, fname), args.claim_lint)
        if problems:
            failed += 1
            print("FAIL %s" % name)
            for p in problems:
                print("     %s" % p)
        else:
            passed += 1
            print("PASS %s" % name)
    print("evals: %d/%d passed" % (passed, passed + failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
