#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure routing decisions only; never execute a tool or request inference."""

import argparse
import json
import math
import statistics
import sys
import time

from nilo import AGENT_NAME, decide_query


CASES = (
    ("what time is it?", "tool", "time"),
    ("puoi darmi la lista file please", "tool", "list_files"),
    ("who am i", "tool", "identity"),
    ("dove mi trovo?", "tool", "directory"),
    ("hostname", "tool", "hostname"),
    ("sistema operativo", "tool", "system"),
    ("uptime", "tool", "uptime"),
    ("disk space", "tool", "disk"),
    ("memoria disponibile", "tool", "memory"),
    ("tell me a joke about time", "system_2", None),
    ("ls; whoami", "system_2", None),
    ("explain ls", "system_2", None),
    ("", "reject", None),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1000, help="Repetitions of the 13-case corpus")
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations must be positive")

    # Warm up and verify expected decisions before measuring latency.
    for query, action, intent in CASES:
        decision = decide_query(query)
        if (decision.action, decision.intent) != (action, intent):
            print(json.dumps({"status": "error", "query": query, "reason": "unexpected routing decision"}))
            return 1

    samples = []
    for _ in range(args.iterations):
        for query, _, _ in CASES:
            start = time.perf_counter_ns()
            decide_query(query)
            samples.append((time.perf_counter_ns() - start) / 1_000_000)
    ordered = sorted(samples)
    print(json.dumps({
        "agent": AGENT_NAME, "status": "success", "scope": "routing_decisions_only",
        "python": sys.version.split()[0], "cases": len(CASES),
        "iterations": args.iterations, "samples": len(samples), "cost_tokens": 0,
        "latency_ms": {
            "mean": round(statistics.mean(samples), 6),
            "p50": round(statistics.median(samples), 6),
            "p95": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 6),
            "max": round(ordered[-1], 6),
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
