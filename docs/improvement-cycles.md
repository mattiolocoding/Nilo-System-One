# Improvement cycles — 2026-10-08

The following bounded cycles were completed on the local checkout. Each cycle used
inspection, changes, and verification before proceeding to the next.

## Cycle 1: naming, documentation, repository consistency

- Renamed the router to `nilo.py` and the suite to `test_nilo.py`.
- Updated Python imports, mock targets, CLI examples, and the CI test command.
- Translated the README to English and renamed CLI environment settings to
  `NILO_MODEL` and `NILO_OLLAMA_URL`.
- Merged the manual upload (`be323ec`) into local history. Both original
  histories are retained; no remote history was rewritten.
- Kept the prepared `.gitignore` and CI workflow, which the manual upload had
  omitted, and excluded uploaded bytecode caches from the resulting tree.
- Verification: 33 tests passed after renaming.

## Cycle 2: conservative routing and robust API inputs

Inspection reproduced a `TypeError` for string timeouts, acceptance of boolean
timeouts, an `AttributeError` for a missing model name, and a `TypeError` for
malformed command arguments.

- Invalid timeout, model, URL, and argv types now produce controlled rejection.
- Overlapping intent patterns fall back with `ambiguous_intent_match`.
- Unused LLM configuration no longer prevents CLI tools or decision inspection.
- Verification: 35 tests passed, including overlap and invalid-input cases.

## Cycle 3: discoverability and measurable routing overhead

- Added `--list-tools` to inspect supported intents without execution.
- Added `benchmark_nilo.py`, with a verified 13-case corpus and explicit
  routing-only timing scope.
- Verification: 38 tests passed with ResourceWarning treated as an error;
  tool listing, decision inspection, and the benchmark ran successfully.

Measured locally with Python 3.14.7 over 1,000 repetitions (13,000 decisions):

| Metric | Milliseconds |
| --- | ---: |
| Mean | 0.003626 |
| p50 | 0.003574 |
| p95 | 0.006116 |
| Maximum | 0.027553 |

These are synthetic routing measurements after warm-up. They exclude process
execution, model inference, and model loading. They do not establish accuracy
on unseen requests or an end-to-end speedup against an LLM.

## Validation limits

Tests ran locally on Linux with Python 3.14.7. The configured CI matrix covers
Python 3.10, 3.12, and 3.14. The first three cycles were published at `d591d0d`
and [passed hosted CI](https://github.com/mattiolocoding/Nilo-System-One/actions/runs/37758947962).
Results for subsequent commits must be checked after publication.

This checkout uses the Apache-2.0 license selected by the maintainer.

## Cycle 4: incomplete HTTP responses and protocol errors

Real loopback HTTP fixtures reproduced three false-success cases (truncated
Content-Length, negative Content-Length, and nonnumeric Content-Length) and
two uncaught exceptions (a malformed status line and truncated chunked data).

- Response lengths are validated before declaring success.
- Conflicting length headers and unsupported transfer encodings are rejected.
- HTTP protocol exceptions return JSON errors with unknown token usage.
- Complete chunked responses remain supported.
- Verification: 43 tests passed, including five new HTTP regression tests.

The implementation handles the [HTTP client exception hierarchy](https://docs.python.org/3/library/http.client.html#http.client.HTTPException)
in addition to socket and URL errors. HTTP timeouts retain their documented
per-operation semantics; this change does not introduce a total-request deadline.
