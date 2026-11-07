#!/usr/bin/env python3
"""Normalize SARIF 2.1.0 findings into reviewable evidence (V2-23).

An adapter does not run an engine. It reads a SARIF log, resolves the engine by
`tool.driver.name`, maps each result by its rule ID through
`spec/sarif/adapters.yaml`, and emits one deterministic finding per result. A
finding whose engine or rule is not configured is `unmapped`; it is not pushed
into `other` and it is not silently dropped.

The report is a review queue and an evidence input, not a verdict. A mapped
finding says "this rule is in the taxonomy"; it does not say the finding is a
real defect, that the engine's data flow is sound, or that the site is
unprotected. A clean run says only that the configured rules produced no
results in this log.

Fixture provenance is explicit. A SARIF document with
`properties.dev-sec-skills/fixture = true` is reported as `fixture: true`, and
`--reject-fixtures` makes a production job refuse it. The three fixtures under
`spec/sarif/fixtures/` are authored documents that follow the engines'
documented shape; they are not captured engine runs.

Exit codes: 0 no gate error, 1 a parse/mapping gate or `--require-engines`
failed, 2 tool, config or reference error.

Usage:
    python3 tools/sarif_evidence.py \
        --config spec/sarif/adapters.yaml \
        --root . \
        spec/sarif/fixtures/*.sarif \
        [--max-unmapped 0] [--require-engines 3] [--reject-fixtures] \
        [--json report.json] [--list]
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import date
from urllib.parse import unquote, urlparse

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

LEVELS = {"none", "note", "warning", "error"}
CELL_RE = re.compile(r"^CELL-[0-9]{3,}$")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def collect_inputs(paths):
    found = []
    for path in paths:
        if os.path.isdir(path):
            for pattern in ("*.sarif", "*.json"):
                found.extend(glob.glob(os.path.join(path, pattern)))
        else:
            found.append(path)
    return sorted(set(found))


def normalize_path(uri, root):
    if not uri:
        return None
    if uri.startswith("file://"):
        uri = urlparse(uri).path
    uri = unquote(uri).replace("\\", "/")
    while uri.startswith("./"):
        uri = uri[2:]
    if root and os.path.isabs(uri):
        try:
            relative = os.path.relpath(uri, root)
            if not relative.startswith(".."):
                uri = relative.replace("\\", "/")
        except ValueError:
            pass
    return uri or None


def normalize_level(result, rule_meta):
    level = result.get("level")
    if level is None and isinstance(rule_meta, dict):
        level = (rule_meta.get("defaultConfiguration") or {}).get("level")
    if level is None:
        kind = result.get("kind")
        level = {"pass": "none", "fail": "error", "review": "warning"}.get(kind)
    if level not in LEVELS:
        level = "warning"
    return level


def fingerprint_of(result):
    prints = result.get("partialFingerprints")
    if isinstance(prints, dict) and prints:
        return json.dumps(prints, sort_keys=True, ensure_ascii=False)
    return None


def load_config(config_path, root, schema):
    config = read_yaml(config_path)
    engines = config.get("engines") or []
    if not engines:
        raise ValueError("config has no engines")
    seen = set()
    for engine in engines:
        eid = engine.get("id")
        name = engine.get("name")
        if not eid or not name:
            raise ValueError("engine entries need id and name")
        if eid in seen:
            raise ValueError("duplicate engine id %r" % eid)
        seen.add(eid)
        for rule in engine.get("rules") or []:
            if not rule.get("id") or not rule.get("match"):
                raise ValueError("engine %r: rule needs id and match" % eid)
            try:
                re.compile(rule["match"])
            except re.error as exc:
                raise ValueError("engine %r rule %r: bad regex: %s"
                                 % (eid, rule.get("id"), exc))
            if rule.get("taxonomy_class") not in schema["taxonomy"] \
                    or rule.get("taxonomy_class") == "other":
                raise ValueError("engine %r rule %r: unknown taxonomy_class %r"
                                 % (eid, rule.get("id"),
                                    rule.get("taxonomy_class")))
            if rule.get("failure_mode") not in schema["failure_modes"] \
                    or rule.get("failure_mode") == "other":
                raise ValueError("engine %r rule %r: unknown failure_mode %r"
                                 % (eid, rule.get("id"),
                                    rule.get("failure_mode")))

    registries = {}
    for alias, rel in (config.get("registries") or {}).items():
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if not os.path.exists(path):
            raise ValueError("registry %r not found: %s" % (alias, path))
        doc = read_yaml(path)
        registries[alias] = {c.get("id") for c in doc.get("cells") or []
                             if c.get("id")}
    return config, engines, registries


def validate_cell(rule, registries):
    cell = rule.get("cell")
    if not cell:
        return None
    if "/" not in cell:
        raise ValueError("rule %r: cell must be <registry>/<CELL-ID>"
                         % rule.get("id"))
    alias, cid = cell.split("/", 1)
    if alias not in registries:
        raise ValueError("rule %r: registry %r not configured"
                         % (rule.get("id"), alias))
    if not CELL_RE.match(cid) or cid not in registries[alias]:
        raise ValueError("rule %r: cell %r does not exist in %r"
                         % (rule.get("id"), cid, alias))
    return cell


def schema_enums(path):
    if not path or not os.path.exists(path):
        return {"taxonomy": {"security", "correctness", "maintainability",
                             "performance"},
                "failure_modes": {"deny", "abort", "rollback", "safe-degrade",
                                  "detect"}}
    doc = json.load(open(path, encoding="utf-8"))
    props = doc["definitions"]["cell"]["properties"]
    return {
        "taxonomy": set(props["taxonomy_class"]["enum"]),
        "failure_modes": set(props["failure_mode"]["enum"]),
    }


def map_rule(engine, rule_id):
    for rule in engine.get("rules") or []:
        if re.search(rule["match"], rule_id or ""):
            return rule
    return None


def run(argv):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="SARIF files or directories")
    ap.add_argument("--config", required=True)
    ap.add_argument("--root", default=".",
                    help="repository root for path rebasing and registries")
    ap.add_argument("--schema", default=os.path.join(
        here, "spec", "conveyor", "cell-registry.schema.json"))
    ap.add_argument("--max-unmapped", type=int, default=None,
                    help="fail when more findings than this are unmapped")
    ap.add_argument("--require-engines", type=int, default=0,
                    help="fail unless at least this many configured engines appear")
    ap.add_argument("--reject-fixtures", action="store_true",
                    help="fail when any input declares fixture provenance")
    ap.add_argument("--json", default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("error: root not found: %s" % root, file=sys.stderr)
        return 2
    if not os.path.exists(args.config):
        print("error: config not found: %s" % args.config, file=sys.stderr)
        return 2

    try:
        schema = schema_enums(args.schema)
        config, engines, registries = load_config(args.config, root, schema)
        for engine in engines:
            for rule in engine.get("rules") or []:
                validate_cell(rule, registries)
    except (OSError, ValueError, yaml.YAMLError, KeyError, json.JSONDecodeError) as exc:
        print("[SARIF3] error  config: %s" % exc, file=sys.stderr)
        return 2

    engine_by_name = {}
    for engine in engines:
        engine_by_name[engine["name"].lower()] = engine
        engine_by_name[engine["id"].lower()] = engine
    files = collect_inputs(args.inputs)
    if not files:
        print("[SARIF1] error  no SARIF input found", file=sys.stderr)
        return 1

    findings = []
    unmapped = []
    inputs = []
    seen = set()
    duplicates = 0
    engine_runs = {}
    gate_errors = []
    fixture_inputs = 0

    for path in files:
        if not os.path.exists(path):
            gate_errors.append("[SARIF1] error  input not found: %s" % path)
            continue
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError) as exc:
            gate_errors.append("[SARIF1] error  %s: invalid JSON: %s"
                               % (path, exc))
            continue
        if doc.get("version") != "2.1.0":
            gate_errors.append("[SARIF1] error  %s: version is %r, expected 2.1.0"
                               % (path, doc.get("version")))
            continue
        runs = doc.get("runs")
        if not isinstance(runs, list) or not runs:
            gate_errors.append("[SARIF1] error  %s: no runs" % path)
            continue

        props = doc.get("properties") or {}
        fixture = bool(props.get("dev-sec-skills/fixture"))
        if any((run.get("properties") or {}).get("dev-sec-skills/fixture")
               for run in runs):
            fixture = True
        if fixture:
            fixture_inputs += 1
            if args.reject_fixtures:
                gate_errors.append("[SARIF1] error  %s: fixture input rejected"
                                   % path)

        names = []
        results_count = 0
        for run in runs:
            driver = (run.get("tool") or {}).get("driver") or {}
            name = driver.get("name")
            if not name:
                gate_errors.append("[SARIF2] error  %s: run has no tool.driver.name"
                                   % path)
                continue
            engine = engine_by_name.get(name.lower()) \
                or engine_by_name.get(name.lower().replace(" ", "-"))
            names.append(name)
            if engine:
                engine_runs[engine["id"]] = engine_runs.get(engine["id"], 0) + 1
            rules_meta = {}
            for rule in driver.get("rules") or []:
                if rule.get("id"):
                    rules_meta[rule["id"]] = rule

            for result in run.get("results") or []:
                results_count += 1
                rule_id = result.get("ruleId") or \
                    (result.get("rule") or {}).get("id")
                if not rule_id:
                    unmapped.append({
                        "engine": engine["id"] if engine else name,
                        "rule_id": None,
                        "path": None,
                        "start_line": None,
                        "reason": "missing-rule-id"})
                    continue

                if not engine:
                    unmapped.append({
                        "engine": name, "rule_id": rule_id,
                        "path": None, "start_line": None,
                        "reason": "unknown-engine"})
                    continue
                rule = map_rule(engine, rule_id)
                if rule is None:
                    unmapped.append({
                        "engine": engine["id"], "rule_id": rule_id,
                        "path": None, "start_line": None,
                        "reason": "unmapped-rule"})
                    continue

                locations = result.get("locations") or []
                physical = (locations[0].get("physicalLocation")
                            if locations else None) or {}
                artifact = physical.get("artifactLocation") or {}
                uri = artifact.get("uri")
                region = physical.get("region") or {}
                start = region.get("startLine")
                end = region.get("endLine", start)
                normalized = normalize_path(uri, root)
                if not normalized:
                    unmapped.append({
                        "engine": engine["id"], "rule_id": rule_id,
                        "path": None, "start_line": None,
                        "reason": "missing-location"})
                    continue

                message = ((result.get("message") or {}).get("text")
                           or (result.get("message") or {}).get("markdown")
                           or "")
                fingerprint = fingerprint_of(result)
                key = (engine["id"], fingerprint or
                       (rule_id, normalized, start, end, message))
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)

                findings.append({
                    "engine": engine["id"],
                    "engine_name": name,
                    "rule_id": rule_id,
                    "level": normalize_level(result, rules_meta.get(rule_id)),
                    "message": message,
                    "path": normalized,
                    "start_line": start,
                    "end_line": end,
                    "fingerprint": fingerprint,
                    "taxonomy_class": rule.get("taxonomy_class"),
                    "failure_class": rule.get("failure_class"),
                    "failure_mode": rule.get("failure_mode"),
                    "cell": rule.get("cell"),
                    "mapped": True,
                })

        inputs.append({
            "path": os.path.relpath(path, root) if os.path.isabs(path)
            else path,
            "sha256": sha256_file(path),
            "engines": sorted(set(names)),
            "runs": len(runs),
            "results": results_count,
            "fixture": fixture,
        })

    findings.sort(key=lambda f: (f["engine"], f["path"] or "", f["start_line"] or 0,
                                 f["rule_id"] or "", f["message"] or "",
                                 f["fingerprint"] or ""))
    for index, finding in enumerate(findings, 1):
        finding["id"] = "F-%03d" % index

    configured = {engine["id"] for engine in engines}
    present = {eid for eid in engine_runs if eid in configured}
    if args.require_engines and len(present) < args.require_engines:
        gate_errors.append(
            "[SARIF2] error  %d configured engine(s) present, need %d"
            % (len(present), args.require_engines))
    if args.max_unmapped is not None and len(unmapped) > args.max_unmapped:
        gate_errors.append(
            "[SARIF2] error  %d unmapped finding(s), limit %d"
            % (len(unmapped), args.max_unmapped))

    digest_payload = [
        {key: finding.get(key) for key in (
            "engine", "rule_id", "level", "message", "path", "start_line",
            "end_line", "fingerprint", "taxonomy_class", "failure_class",
            "failure_mode", "cell", "mapped")}
        for finding in findings]
    digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, ensure_ascii=False)
        .encode("utf-8")).hexdigest()

    by_engine = []
    for engine in engines:
        own = [f for f in findings if f["engine"] == engine["id"]]
        own_unmapped = [u for u in unmapped if u["engine"] == engine["id"]]
        by_engine.append({
            "id": engine["id"], "name": engine["name"],
            "runs": engine_runs.get(engine["id"], 0),
            "findings": len(own), "unmapped": len(own_unmapped),
            "cell_mapped": len([f for f in own if f.get("cell")]),
        })

    report = {
        "format": "dev-sec-skills/sarif-evidence/v1",
        "generated": date.today().isoformat(),
        "inputs": inputs,
        "engines": by_engine,
        "present_engines": sorted(present),
        "findings": findings,
        "unmapped": unmapped,
        "summary": {
            "inputs": len(inputs),
            "fixture_inputs": fixture_inputs,
            "findings": len(findings),
            "mapped": len(findings),
            "unmapped": len(unmapped),
            "duplicates": duplicates,
            "cell_mapped": len([f for f in findings if f.get("cell")]),
            "engines_present": len(present),
            "digest": digest,
        },
        "errors": gate_errors,
    }

    for error in gate_errors:
        print(error, file=sys.stderr)
    if args.list:
        for finding in findings:
            print("FIND     %-8s %-9s %-8s %s:%s  %s"
                  % (finding["engine"], finding["level"],
                     finding["cell"] or "-", finding["path"],
                     finding["start_line"], finding["rule_id"]))
    for item in unmapped:
        print("UNMAPPED %-10s %-30s %s"
              % (item["engine"], item["rule_id"], item["reason"]))
    for engine in by_engine:
        print("ENGINE   %-10s %-28s runs=%d findings=%d unmapped=%d cell=%d"
              % (engine["id"], engine["name"], engine["runs"],
                 engine["findings"], engine["unmapped"], engine["cell_mapped"]))
    print("sarif: %d input(s), %d engine(s) present, %d finding(s), "
          "%d unmapped, %d duplicate(s), %d fixture input(s), digest %s"
          % (len(inputs), len(present), len(findings), len(unmapped),
             duplicates, fixture_inputs, digest[:16]))

    if args.json:
        parent = os.path.dirname(os.path.abspath(args.json))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return 1 if gate_errors else 0


def main():
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
