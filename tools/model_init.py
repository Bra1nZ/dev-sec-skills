#!/usr/bin/env python3
"""Step 0: create the working directory for one target.

Writes the skeleton that later steps fill: an empty ``bounds.yaml.example``
(no numbers, and a comment saying why), and a ``JOURNAL.md`` with one empty
iteration. It does not create primitives or decisions: those are outputs of
``model-extract`` and ``model-review``, and inventing them here would make a
fresh directory look like a run.

Exit codes: 0 ok, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from model_primitives import (
    add_target_args, default_out, prepare, sha256_file,
)

BOUNDS_EXAMPLE = """\
# Bounds are set by whoever runs the conveyor, not by the tool.
#
# Copy this file to `bounds.yaml` and replace every value with a number you can
# justify for this project. The `rationale` is mandatory: a bound without a
# reason is a guess wearing a number.
#
# Without bounds.yaml the run cannot exceed `tested`. V0 does not claim
# `model-checked` even with the file, because it has no bounded enumerator
# behind it; the file is recorded until that enumerator exists.
#
# bounds:
#   max_instances: <how many values per variable to enumerate>
#   max_depth: <how deep a transition trace to explore>
#   max_states: <a stop that protects the machine>
#   rationale: "<why these numbers cover the behaviour you care about>"
"""

JOURNAL = """\
# Agent journal

One section per iteration. Append; never rewrite an earlier section.

## Iteration 1 — <date>

### Намерение
Что собирался получить и почему именно так.

### Команды
Точные команды, без сокращений.

### Факт
Что реально получилось: числа, пути, коды возврата.

### Расхождение с ожиданием
Где результат не совпал с намерением. Это самое ценное место.

### Решения
Что выбрал и по какой причине, включая `rejected` и `no-guard-ok`.

### Блокеры и вопросы
Что не смог без человека.

### Что предлагаю изменить в инструменте
Шаг, вход, ожидаемое поведение.
"""


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="Create the model working directory for a target.")
    add_target_args(ap)
    args = ap.parse_args(argv)

    info, out, console, journal = prepare(args, "init")
    started = time.time()
    try:
        example = os.path.join(out, "bounds.yaml.example")
        if not os.path.isfile(example):
            with open(example, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(BOUNDS_EXAMPLE)
        journal_path = os.path.join(out, "JOURNAL.md")
        if not os.path.isfile(journal_path):
            with open(journal_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(JOURNAL)
        console("init: %s" % out)
        console("  target      %s" % info["path"])
        console("  commit      %s%s" % (info["commit"] or "none",
                                        " (dirty)" if info["dirty"] else ""))
        extra = "" if out == default_out(info["path"]) else \
            " MODEL_OUT=%s" % out
        console("  next        make model-scan TARGET=%s%s"
                % (info["path"], extra))
        print("init: %s" % out)
        journal.write(
            argv=sys.argv[1:], target=info["path"],
            target_commit=info["commit"], dirty=info["dirty"],
            exit_code=0,
            duration_ms=int((time.time() - started) * 1000),
            outputs=[{"path": example, "sha256": sha256_file(example)},
                     {"path": journal_path,
                      "sha256": sha256_file(journal_path)}],
            counts={"files": 2}, status="ok",
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - a crash must still be journaled
        journal_crash(console, journal, exc, started, argv=sys.argv[1:],
                      target=info["path"], target_commit=info["commit"],
                      dirty=info["dirty"])
        return 2
    finally:
        console.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
