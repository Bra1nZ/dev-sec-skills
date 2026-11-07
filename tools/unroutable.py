#!/usr/bin/env python3
"""U — the unroutable share of the cell taxonomy (V2-25).

Formula, fixed with the threshold and repeated here so the number cannot be
recalculated under another definition:

    numerator   cells whose taxonomy_class is 'other' or whose failure_mode
                is 'other' (the escape hatch, which requires routing_note)
    denominator all cells of all registries passed on the measurement date

The share is reported as a percentage. Use --max-share to turn the number into
a gate: a new 'other' cell fails the run until a new artifact and a new
threshold are recorded in spec/conveyor/product-trials.md (§2.1).

Before V2-25 the schema rejected an undeclared class or mode, so a cell that
did not route could not reach a counted registry and the share was always 0.
With the escape hatch a non-routing cell is representable, so 0 is an
observation, not a structural impossibility.

Usage:
    python3 tools/unroutable.py [--max-share PERCENT] registry.yaml [...]
"""

import argparse
import json
import os
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


def load_doc(path):
    text = open(path, encoding="utf-8").read()
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise SystemExit("PyYAML is required for YAML registries; pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def main():
    ap = argparse.ArgumentParser(description="Measure the unroutable share U")
    ap.add_argument("registries", nargs="+", help="cell registry files (YAML or JSON)")
    ap.add_argument("--max-share", type=float, default=None,
                    help="fail when the overall share exceeds this percentage "
                         "(0 means any 'other' cell fails)")
    args = ap.parse_args()

    print("U = cells whose taxonomy_class or failure_mode is 'other' / all cells")
    print("%-34s %6s %6s %6s %6s %8s" %
          ("registry", "cells", "class", "mode", "unrout", "share"))
    errors = 0
    total_cells = total_unroutable = 0
    for path in args.registries:
        if not os.path.isfile(path):
            print("registry not found: %s" % path, file=sys.stderr)
            return 2
        try:
            doc = load_doc(path)
        except (OSError, ValueError) as e:
            print("cannot load %s: %s" % (path, e), file=sys.stderr)
            return 2
        cells = doc.get("cells") if isinstance(doc, dict) else None
        if not isinstance(cells, list) or not cells:
            print("no cells array in %s" % path, file=sys.stderr)
            return 2

        class_other = mode_other = unroutable = 0
        for cell in cells:
            if not isinstance(cell, dict):
                print("non-object cell in %s" % path, file=sys.stderr)
                return 2
            cls_other = cell.get("taxonomy_class") == "other"
            mode_other_hit = cell.get("failure_mode") == "other"
            if not (cls_other or mode_other_hit):
                continue
            note = cell.get("routing_note")
            if not isinstance(note, str) or not note.strip():
                print("error: %s %s uses 'other' without routing_note"
                      % (path, cell.get("id", "-")), file=sys.stderr)
                errors += 1
            class_other += int(cls_other)
            mode_other += int(mode_other_hit)
            unroutable += 1
            print("  other: %-10s class=%-5s mode=%-5s %s"
                  % (cell.get("id", "-"), cls_other, mode_other_hit,
                     (note or "<no routing_note>").strip()))

        share = 100.0 * unroutable / len(cells)
        total_cells += len(cells)
        total_unroutable += unroutable
        print("%-34s %6d %6d %6d %6d %7.1f%%"
              % (os.path.basename(os.path.dirname(os.path.abspath(path))) + "/"
                 + os.path.basename(path), len(cells), class_other, mode_other,
                 unroutable, share))

    total_share = 100.0 * total_unroutable / total_cells if total_cells else 0.0
    print("%-34s %6d %6s %6s %6d %7.1f%%"
          % ("total", total_cells, "", "", total_unroutable, total_share))

    if errors:
        return 2
    if args.max_share is not None and total_share > args.max_share + 1e-9:
        print("error: unroutable share %.1f%% exceeds the fixed U %.1f%%; "
              "a new artifact and a new threshold are required"
              % (total_share, args.max_share), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
