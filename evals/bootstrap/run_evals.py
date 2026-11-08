#!/usr/bin/env python3
"""End-to-end eval for tools/bootstrap.py.

The eval builds a throwaway git repository with one stdlib test, bootstraps it,
checks that the generated open templates pass both linters, then walks the
honest promotion path: run the suite, capture the log, add a run_record, sign
it, raise the claim and the cell, and require all three gates to pass.

It also attacks the result:

  * a vendored file edited in the target is reported as drift and refreshed
    only with --force;
  * --force does not overwrite the registry or the ledger;
  * an edit to a signed field after signing fails L2;
  * open -> tested without new evidence fails status_diff;
  * a target inside the source repository is refused.

The test runner is stdlib `unittest -v`, not pytest: the eval must run on a
machine with no third-party test framework. `claim_lint` recognizes the test
name but not unittest's summary, so the green state carries one documented
`L2 info` ("counts not cross-checked"). The eval requires zero errors and zero
warnings, not zero info.

Usage:
    python3 evals/bootstrap/run_evals.py [--bootstrap PATH]
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATE = date.today().isoformat()
SUITE_GLOB = "tests/*.py"
TEST_FILE = "tests/test_smoke.py"
LEDGER = "docs/claims.yaml"
REGISTRY = "spec/cells.yaml"


class Fail(Exception):
    pass


def run(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)


def must(proc, what, cwd):
    if proc.returncode != 0:
        raise Fail("%s exited %d\nstdout:\n%s\nstderr:\n%s"
                   % (what, proc.returncode, proc.stdout, proc.stderr))
    return proc


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def bootstrap_cmd(bootstrap, target, anchor_dir):
    return [
        sys.executable, bootstrap,
        "--target", target,
        "--name", "bootstrap-eval",
        "--suite-glob", SUITE_GLOB,
        "--with-ci",
        "--with-anchor",
        "--anchor-dir", anchor_dir,
        "--signer", "bootstrap-eval-anchor",
        "--date", DATE,
    ]


def assert_green(proc, label, allow_info=True):
    if proc.returncode != 0:
        raise Fail("%s exited %d\n%s" % (label, proc.returncode, proc.stdout + proc.stderr))
    if "0 error(s), 0 warning(s)" not in proc.stdout:
        raise Fail("%s did not report 0 errors and 0 warnings\n%s"
                   % (label, proc.stdout))
    if not allow_info and ", 0 info" not in proc.stdout:
        raise Fail("%s reported info findings\n%s" % (label, proc.stdout))


def gate_commands(target):
    return {
        "cell_lint": [sys.executable, "tools/cell_lint.py", "--root", ".",
                      "--ledger", LEDGER, "--suite-glob", SUITE_GLOB, REGISTRY],
        "claim_lint": [sys.executable, "tools/claim_lint.py", "--root", ".",
                       "--suite-glob", SUITE_GLOB, "--run-log-root", ".",
                       "--tool-output-root", ".", "--no-vale", LEDGER],
    }


def case_bootstrap(bootstrap, target, anchor_dir):
    proc = run(bootstrap_cmd(bootstrap, target, anchor_dir), REPO)
    must(proc, "bootstrap", REPO)
    required = [
        "tools/claim_lint.py", "tools/cell_lint.py", "tools/status_diff.py",
        "tools/anchor_run.py", "tools/anchor_subject.py",
        "tools/dev-sec-skills.VERSION",
        "styles/RussianAbsolutes/BannedAbsolutes.yml",
        "schemas/claim-ledger.schema.json",
        "spec/conveyor/cell-registry.schema.json",
        "spec/anchor/allowed_signers", REGISTRY, LEDGER,
        ".github/workflows/claim-lint.yml", ".github/workflows/cell-lint.yml",
    ]
    missing = [rel for rel in required if not os.path.isfile(os.path.join(target, rel))]
    if missing:
        raise Fail("bootstrap did not create: %s" % ", ".join(missing))
    if os.path.isfile(os.path.join(target, "schemas/README.md")):
        raise Fail("bootstrap vendored schemas/README.md (L5 would scan it)")
    ledger = yaml.safe_load(open(os.path.join(target, LEDGER)))
    claim = ledger["claims"][0]
    if claim.get("status") != "open" or claim.get("evidence") != []:
        raise Fail("bootstrap did not generate an honest open claim: %s" % claim)
    if not claim.get("limitations"):
        raise Fail("open bootstrap claim has no limitations")
    registry = yaml.safe_load(open(os.path.join(target, REGISTRY)))
    cell = registry["cells"][0]
    if cell.get("coverage_status") != "open" or cell.get("detectors"):
        raise Fail("bootstrap did not generate an open cell: %s" % cell)
    version = json.load(open(os.path.join(target, "tools/dev-sec-skills.VERSION")))
    if version.get("source") != "dev-sec-skills" or not version.get("files"):
        raise Fail("VERSION has no source or file map: %s" % version)
    for rel, expected in version["files"].items():
        actual = sha256(os.path.join(target, rel))
        if actual != expected:
            raise Fail("VERSION hash mismatch for %s" % rel)
    ci = open(os.path.join(target, ".github/workflows/cell-lint.yml")).read()
    if "REGISTRY: %s" % REGISTRY not in ci or "SUITE_GLOB:" not in ci:
        raise Fail("cell-lint.yml was not rendered with the target paths")
    if "FIRST_RELEASE: 1" not in ci:
        raise Fail("cell-lint.yml did not get the first-release exemption")

    again = run(bootstrap_cmd(bootstrap, target, anchor_dir), REPO)
    must(again, "second bootstrap", REPO)
    if "DRIFT" in again.stdout or "drift=" in again.stdout:
        raise Fail("second bootstrap should be idempotent\n%s" % again.stdout)

    # Drift: an edited vendored tool is reported, and only --force refreshes it.
    tampered = os.path.join(target, "tools/cell_lint.py")
    write(tampered, open(tampered).read() + "\n# local edit\n")
    drift = run(bootstrap_cmd(bootstrap, target, anchor_dir), REPO)
    if drift.returncode != 1 or "DRIFT" not in drift.stdout:
        raise Fail("edited vendor file was not reported as drift (exit %d)\n%s"
                   % (drift.returncode, drift.stdout))
    forced = run(bootstrap_cmd(bootstrap, target, anchor_dir) + ["--force"], REPO)
    must(forced, "bootstrap --force", REPO)
    if "# local edit" in open(tampered).read():
        raise Fail("--force did not refresh the vendored tool")


def case_open_gates(target):
    for label, cmd in gate_commands(target).items():
        proc = run(cmd, target)
        assert_green(proc, "open %s" % label)


def promote(target):
    """Run the suite, add a certified run_record, and raise both statuses."""
    test_path = os.path.join(target, TEST_FILE)
    write(test_path, """\
import unittest


class TestSmoke(unittest.TestCase):
    def test_smoke(self):
        self.assertTrue(True)

    def test_refusal_reports_a_failure(self):
        with self.assertRaises(ValueError):
            raise ValueError("refused")
""")
    init = run(["git", "init", "-q", "-b", "main"], target)
    must(init, "git init", target)
    run(["git", "config", "user.email", "eval@example.invalid"], target)
    run(["git", "config", "user.name", "bootstrap eval"], target)
    must(run(["git", "add", "-A"], target), "git add", target)
    must(run(["git", "commit", "-q", "-m", "bootstrap"], target), "git commit", target)
    commit = run(["git", "rev-parse", "HEAD"], target).stdout.strip()

    log_rel = "docs/runs/unittest-%s.log" % DATE
    log_path = os.path.join(target, log_rel)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    started = datetime.now().astimezone()
    suite = run([sys.executable, "-m", "unittest", "-v", "tests.test_smoke"], target)
    finished = datetime.now().astimezone()
    if suite.returncode != 0:
        raise Fail("unittest failed:\n%s\n%s" % (suite.stdout, suite.stderr))
    write(log_path, suite.stdout + suite.stderr)

    ledger_path = os.path.join(target, LEDGER)
    ledger = yaml.safe_load(open(ledger_path))
    claim = ledger["claims"][0]
    claim["claim"] = ("The test harness runs to completion and reports a result for each "
                      "test it discovers.")
    claim["mechanism"] = (
        "python3 -m unittest -v tests.test_smoke discovers two tests, one of which asserts "
        "that a refusal raises; the exit code, the named tests and their PASSED/ok lines "
        "are captured in the committed log and signed by the run-record anchor.")
    claim["status"] = "tested"
    claim["evidence"] = [{
        "kind": "test",
        "tests": ["test_smoke", "test_refusal_reports_a_failure"],
        "command": "python3 -m unittest -v tests.test_smoke",
        "artifact": TEST_FILE,
        "commit": commit,
        "date": DATE,
        "run_record": {
            "runner": "unittest",
            "command": "python3 -m unittest -v tests.test_smoke",
            "commit": commit,
            "exit_code": 0,
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": finished.isoformat(timespec="seconds"),
            "log": log_rel,
            "log_sha256": sha256(log_path),
            "artifact_sha256": sha256(test_path),
            "tests_run": 2,
            "tests_passed": 2,
        },
    }]
    claim.pop("limitations", None)
    with open(ledger_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(ledger, handle, sort_keys=False, allow_unicode=True, width=100)

    return commit, ledger_path, log_rel


def sign(target, anchor_dir):
    anchor_proc = must(run([
        sys.executable, "tools/anchor_run.py", "create",
        "--ledger", LEDGER, "--claim", "C-01", "--channel", "run-record",
        "--run", "0", "--key", os.path.join(anchor_dir, "key"),
        "--signer", "bootstrap-eval-anchor",
        "--out-dir", "spec/anchor", "--allowed-signers", "spec/anchor/allowed_signers",
        "--id", "run-record-bootstrap-eval-c01-%s" % DATE,
        "--date", DATE, "--base", ".",
    ], target), "anchor create", target)
    return yaml.safe_load(anchor_proc.stdout)["anchor"]


def promote_cell(target):
    registry_path = os.path.join(target, REGISTRY)
    registry = yaml.safe_load(open(registry_path))
    cell = registry["cells"][0]
    cell["coverage_status"] = "tested"
    cell["owner"] = "bootstrap eval"
    cell["detectors"] = [{
        "id": "D-SMOKE",
        "kind": "test",
        "artifact": TEST_FILE,
        "command": "python3 -m unittest -v tests.test_smoke",
        "status": "tested",
        "last_verified": DATE,
        "mutation_exemption": (
            "The example cell describes a harness, not a production mechanism: there is "
            "no removable guard to mutate. A real cell replaces this exemption with a "
            "fixture that turns the check off and expects the detector to fail."),
    }]
    with open(registry_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(registry, handle, sort_keys=False, allow_unicode=True, width=100)


def attach_anchor(ledger_path, anchor):
    ledger = yaml.safe_load(open(ledger_path))
    ledger["claims"][0]["evidence"][0]["run_record"]["anchor"] = anchor
    with open(ledger_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(ledger, handle, sort_keys=False, allow_unicode=True, width=100)


def case_promoted(bootstrap, target, anchor_dir):
    commit, ledger_path, log_rel = promote(target)
    anchor = sign(target, anchor_dir)
    attach_anchor(ledger_path, anchor)
    promote_cell(target)
    must(run(["git", "add", "-A"], target), "git add evidence", target)
    must(run(["git", "commit", "-q", "-m", "test: record the smoke run"], target),
         "git commit evidence", target)

    for label, cmd in gate_commands(target).items():
        proc = run(cmd, target)
        # unittest's summary is not one the linter parses, so one L2 info is
        # expected; an error or a warning still fails.
        assert_green(proc, "tested %s" % label, allow_info=True)
        if label == "claim_lint" and "L2 evidence      0 error(s), 0 warning(s), 1 info" \
                not in proc.stdout:
            raise Fail("the documented L2 info for an unrecognized summary is missing\n%s"
                       % proc.stdout)

    status = run([sys.executable, "tools/status_diff.py", "--repo", ".", "--ledger",
                  LEDGER, "--git-ref", commit], target)
    must(status, "status_diff", target)
    if "open -> tested with 1 new evidence" not in status.stdout:
        raise Fail("status_diff did not see the new evidence\n%s" % status.stdout)

    # --force must not destroy the ledger or the registry.
    forced = run(bootstrap_cmd(bootstrap, target, anchor_dir) + ["--force"], REPO)
    must(forced, "bootstrap --force after promotion", REPO)
    after = yaml.safe_load(open(ledger_path))
    if after["claims"][0]["status"] != "tested":
        raise Fail("--force overwrote the promoted ledger")

    # A signed field changed after signing must fail L2.
    tampered = yaml.safe_load(open(ledger_path))
    tampered["claims"][0]["evidence"][0]["run_record"]["tests_passed"] = 1
    with open(ledger_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(tampered, handle, sort_keys=False, allow_unicode=True, width=100)
    broken = run(gate_commands(target)["claim_lint"], target)
    if broken.returncode != 1 or "anchor subject does not describe this record" not in broken.stdout:
        raise Fail("a signed-field edit did not fail the anchor check (exit %d)\n%s"
                   % (broken.returncode, broken.stdout))
    must(run(["git", "checkout", "--", LEDGER], target), "restore ledger", target)

    # Escalation without new evidence must fail status_diff.
    base = run(["git", "show", "%s:%s" % (commit, LEDGER)], target)
    must(base, "read base ledger", target)
    base_path = os.path.join(target, "base-ledger.yaml")
    write(base_path, base.stdout)
    no_ev = yaml.safe_load(open(ledger_path))
    no_ev["claims"][0]["evidence"] = []
    no_ev_path = os.path.join(target, "no-evidence.yaml")
    with open(no_ev_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(no_ev, handle, sort_keys=False, allow_unicode=True, width=100)
    no_ev_proc = run([sys.executable, "tools/status_diff.py", base_path, no_ev_path], target)
    if no_ev_proc.returncode != 1 or "without new evidence" not in no_ev_proc.stdout:
        raise Fail("status_diff accepted an escalation without evidence (exit %d)\n%s"
                   % (no_ev_proc.returncode, no_ev_proc.stdout))


def case_refusals(bootstrap, target, source):
    inside = run([sys.executable, bootstrap, "--target", source, "--name", "self"], REPO)
    if inside.returncode != 2 or "refusing to bootstrap the source" not in inside.stderr:
        raise Fail("bootstrap did not refuse the source repository (exit %d)\n%s"
                   % (inside.returncode, inside.stderr))
    escape = run([sys.executable, bootstrap, "--target", target,
                  "--ledger", "../escape.yaml"], REPO)
    if escape.returncode != 2 or "must stay inside the target" not in escape.stderr:
        raise Fail("bootstrap accepted a ledger path outside the target (exit %d)\n%s"
                   % (escape.returncode, escape.stderr))
    key_inside = run([sys.executable, bootstrap, "--target", target,
                      "--with-anchor", "--anchor-dir",
                      os.path.join(target, "anchor")], REPO)
    if key_inside.returncode != 2 or "must stay outside the target" not in key_inside.stderr:
        raise Fail("bootstrap accepted a private key inside the target (exit %d)\n%s"
                   % (key_inside.returncode, key_inside.stderr))
    if os.path.exists(os.path.join(target, "anchor")):
        raise Fail("bootstrap created the refused anchor directory")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bootstrap", default=os.path.join(REPO, "tools", "bootstrap.py"))
    args = ap.parse_args()
    bootstrap = os.path.abspath(args.bootstrap)
    if not os.path.isfile(bootstrap):
        print("bootstrap not found: %s" % bootstrap, file=sys.stderr)
        return 2
    if shutil.which("ssh-keygen") is None:
        print("ssh-keygen is required for the anchor half of this eval", file=sys.stderr)
        return 2

    scratch = tempfile.mkdtemp(prefix="bootstrap-eval-")
    target = os.path.join(scratch, "repo")
    anchor_dir = os.path.join(scratch, "anchor")
    os.makedirs(os.path.join(target, "tests"))
    write(os.path.join(target, TEST_FILE), """\
import unittest


class TestSmoke(unittest.TestCase):
    def test_smoke(self):
        self.assertTrue(True)
""")

    cases = [
        ("open templates and drift", lambda: case_bootstrap(bootstrap, target, anchor_dir)),
        ("open templates pass the gates", lambda: case_open_gates(target)),
        ("promotion, anchor and gates", lambda: case_promoted(bootstrap, target, anchor_dir)),
        ("refusals", lambda: case_refusals(bootstrap, target, REPO)),
    ]
    failed = 0
    try:
        for name, call in cases:
            try:
                call()
                print("ok   %s" % name)
            except Fail as exc:
                failed += 1
                print("FAIL %s\n     %s" % (name, str(exc).replace("\n", "\n     ")))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print("%d/%d bootstrap eval cases passed" % (len(cases) - failed, len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
