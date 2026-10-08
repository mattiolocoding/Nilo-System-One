#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run frozen choice tasks without executing any selected tool."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import time

from benchmarks.adapters import load_adapter


def read_dataset(path):
    raw = Path(path).read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    ids = set()
    for row in rows:
        required = {"id", "track", "split", "language", "category", "state", "question", "options", "gold"}
        if not required <= row.keys() or row["id"] in ids:
            raise ValueError("Missing fields or duplicate case ID")
        ids.add(row["id"])
        options = row["options"]
        if not isinstance(options, dict) or len(options) < 2 or row["gold"] not in options:
            raise ValueError(f"Invalid options/gold in {row['id']}")
        if any(not isinstance(k, str) or not isinstance(v, str) or not k or not v for k, v in options.items()):
            raise ValueError("Option IDs and descriptions must be nonempty strings")
        if row["track"] not in ("routing", "general") or row["split"] not in ("dev", "eval"):
            raise ValueError("Invalid track/split")
    if not rows:
        raise ValueError("Empty dataset")
    return rows, hashlib.sha256(raw).hexdigest()


def request_for(row, rng):
    """Only task inputs reach an adapter; never gold, split, language or case ID."""
    pairs = list(row["options"].items())
    rng.shuffle(pairs)
    return {"state": row["state"], "questions": {"decision": {
        "type": "choice", "instructions": row["question"], "criteria": dict(pairs),
    }}}


def validate_answer(answer, options):
    if not isinstance(answer, dict):
        raise ValueError("Adapter must return an object")
    choice = answer.get("choice")
    if choice is not None and (not isinstance(choice, str) or choice not in options):
        raise ValueError("Unknown choice ID")
    probabilities = answer.get("probabilities")
    if probabilities is not None:
        if not isinstance(probabilities, dict) or set(probabilities) != set(options):
            raise ValueError("Probability keys must match the supplied candidates")
        if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
               for p in probabilities.values()):
            raise ValueError("Invalid probability")
        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-5):
            raise ValueError("Probabilities must sum to one")
    return answer


def latency(values):
    if not values:
        return None
    ordered = sorted(values)
    return {"mean": statistics.mean(values), "p50": statistics.median(values),
            "p95": ordered[math.ceil(0.95 * len(ordered)) - 1], "max": ordered[-1]}


def summarize(rows):
    """Errors and abstentions remain in the accuracy denominator."""
    n = len(rows)
    if not n:
        raise ValueError("No measured attempts")
    valid = [r for r in rows if r["status"] == "ok"]
    answered = [r for r in valid if r["choice"] is not None]
    result = {
        "attempts": n, "unique_cases": len({r["id"] for r in rows}),
        "correct": sum(r["correct"] for r in rows),
        "accuracy": sum(r["correct"] for r in rows) / n,
        "error_rate": (n - len(valid)) / n,
        "abstention_rate": sum(r["choice"] is None for r in valid) / n,
        "coverage": len(answered) / n,
        "latency_ms_all": latency([r["elapsed_ms"] for r in rows]),
        "latency_ms_valid": latency([r["elapsed_ms"] for r in valid]),
        "accuracy_by_language": {}, "accuracy_by_category": {},
    }
    for field in ("language", "category"):
        for value in sorted({r[field] for r in rows}):
            group = [r for r in rows if r[field] == value]
            result[f"accuracy_by_{field}"][value] = {
                "correct": sum(r["correct"] for r in group), "attempts": len(group),
                "accuracy": sum(r["correct"] for r in group) / len(group),
            }
    if rows[0]["track"] == "routing":
        negatives = [r for r in rows if r["gold"] in ("system_2", "reject")]
        result["false_tool_selections"] = sum(r["choice"] not in (None, "system_2", "reject") for r in negatives)
        result["non_tool_attempts"] = len(negatives)
    return result


def git_head(path):
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="Inspected upstream checkout (optional)")
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("cases.jsonl"))
    parser.add_argument("--track", choices=("routing", "general"), required=True)
    parser.add_argument("--split", choices=("dev", "eval"), default="eval")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    all_rows, digest = read_dataset(args.dataset)
    rows = [r for r in all_rows if r["track"] == args.track and r["split"] == args.split]
    warmups = [r for r in all_rows if r["track"] == args.track and r["split"] == "dev"][:2]
    if not rows or not warmups:
        parser.error("Both measured cases and dev warmups are required")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.source:
        config["source"] = str(args.source.resolve())
    if config["adapter"] == "nilo" and args.track != "routing":
        parser.error("Nilo's regex router only supports routing; select nilo-ollama for general decisions")
    # Create-only artifacts prevent a rerun from silently replacing bad results.
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1, "status": "loading", "config": config,
        "dataset_sha256": digest, "track": args.track, "split": args.split,
        "repeats": args.repeats, "seed": args.seed, "case_ids": [r["id"] for r in rows],
        "python": platform.python_version(), "platform": platform.platform(),
        "cpu_count": os.cpu_count(), "processor": platform.processor(),
        "packages": {d.metadata.get("Name"): d.version for d in importlib.metadata.distributions()
                     if d.metadata.get("Name")},
        "nilo_revision": git_head(Path(__file__).resolve().parent.parent),
        "code_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (Path(__file__), Path(__file__).with_name("adapters.py"),
                                  Path(__file__).parent.parent / "nilo.py",
                                  Path(__file__).parent.parent / "nilo_patterns.py",
                                  Path(__file__).parent.parent / "nilo_decisions.py")},
        "upstream_revision": git_head(config["source"]) if config.get("source") else None,
        "timing_scope": "serial batch=1 wall time including adapter/serialization; model load and dev warmup excluded",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "accuracy_unit": "attempt; repetitions are not independent new examples",
    }
    manifest_path = args.output / "manifest.json"
    def save_manifest():
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    save_manifest()
    try:
        start = time.perf_counter()
        adapter, metadata = load_adapter(config)
        manifest.update(load_seconds=time.perf_counter() - start, runtime=metadata, status="warming")
        save_manifest()
        start = time.perf_counter()
        for row in warmups:
            request = request_for(row, random.Random(args.seed))
            validate_answer(adapter(request), row["options"])
        manifest.update(warmup_seconds=time.perf_counter() - start, status="running")
        save_manifest()
        measured = []
        with (args.output / "predictions.jsonl").open("x", encoding="utf-8") as stream:
            for repeat in range(args.repeats):
                rng = random.Random(args.seed + repeat)
                order = rows.copy()
                rng.shuffle(order)
                for row in order:
                    request = request_for(row, rng)
                    result = {k: row[k] for k in ("id", "track", "language", "category", "gold")}
                    result.update(repeat=repeat, option_order=list(request["questions"]["decision"]["criteria"]))
                    start = time.perf_counter_ns()
                    try:
                        answer = validate_answer(adapter(request), row["options"])
                        result.update(status="ok", **answer)
                    except Exception as exc:
                        result.update(status="error", choice=None, error=f"{type(exc).__name__}: {exc}")
                    result["elapsed_ms"] = (time.perf_counter_ns() - start) / 1_000_000
                    result["correct"] = result["status"] == "ok" and result["choice"] == row["gold"]
                    measured.append(result)
                    stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
                    stream.flush()
        report = summarize(measured)
        (args.output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        manifest["status"] = "complete"
        print(json.dumps(report, indent=2))
    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        save_manifest()


if __name__ == "__main__":
    main()
