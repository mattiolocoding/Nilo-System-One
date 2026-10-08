# Decision benchmark pilot

Two separate tasks: **routing** (49 evaluation cases, 11 candidates) and
**general policy decisions** (30 evaluation cases, 3–4 candidates).
These are small, authored challenge fixtures, not an independent held-out benchmark
or evidence of state-of-the-art quality. The author has seen the labels. Training-data
overlap with upstream models is unknown. General cases cover English, Italian,
French, Spanish, German and Chinese; this does not test 100-language coverage.

Routing measures selection only: no command is executed. Negations, shell syntax,
extra arguments and compound requests must defer. General cases cover support,
sentiment, access rules, stock thresholds and evidence. Missing information is an
explicit candidate available to every system, not an engine-specific abstention.

## Run

From the repository root, with standard Python:

```bash
python3 -m benchmarks.run --config benchmarks/configs/nilo.json --track routing --output /tmp/nilo-routing-run1
```

The output directory must not exist. It receives a manifest, one JSONL record per
attempt and a summary. Use `--split dev` for development; freeze evaluation fixtures
before improvements and keep before/after results. Repeated trials are not new
independent examples. This pilot supports comparisons, not a universal winner.

Heavy backends are optional and must be installed in separate environments using
their upstream requirements. Pass the selected environment's Python to the same
command. Configs pin Hugging Face revisions; Rizzo uses upstream's pinned 1.7B
Q4_K_M weights. For source-only packages (SemIf and NanoJev), add a `source` key to
a local config pointing to the upstream checkout. Source paths are inserted into
Python's import path and should only point to trusted, inspected checkouts.
Rizzo expects its downloaded `models/` and `runtimes/` in the current directory;
use `PYTHONPATH=/absolute/path/to/Nilo-System-One` when running from that directory.

Adapters use official native inference paths. Kev's evaluation wrapper requires a
label field; the adapter provides the first candidate as a dummy, never the gold
label. Nilo regex has no probability distribution and supports routing only.
`nilo-ollama` is a separate generative baseline through Nilo's existing System 2
client, with a fixed choice prompt, and includes loopback HTTP overhead. Its token
count is not zero. NanoJev's official prototype requires CUDA; its games-trained
checkpoint is evaluated outside its training domain here.

## Measurement rules

- Serial, batch size one; no answer cache. Same cases and seeded candidate/order
  permutations for every backend. Backend-specific official serialization remains.
- Time includes the adapter, tokenization and output validation. Model loading and
  two development warmups are recorded separately. CLI startup is excluded.
- All errors and abstentions count against accuracy. Report latency for all attempts
  and valid responses separately; a fast failure is not a fast correct decision.
- Report false tool selections on routing negatives, language/category accuracy,
  coverage, errors, p50 and p95. Model probabilities are not assumed calibrated.
- Compare latency only alongside device, quantization, model size, thread count and
  transport. CPU native, GPU native and HTTP results are separate execution profiles.
- Record dataset SHA256, revisions, package versions and each prediction. Never mix
  upstream published scores into locally measured rankings. Failed setup is unranked.

Upstreams: [Kev](https://github.com/jaredpalmer/kev),
[Laya](https://github.com/NandhaKishorM/laya),
[SemIf](https://github.com/TheoLeeCJ/SemIf-OpenJev),
[Rizzo Flow](https://github.com/Rizzo-AI-Academy/rizzo-flow),
[NanoJev](https://github.com/TianyuCodings/NanoJev).
