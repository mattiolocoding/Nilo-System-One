# Nilo — System One

Nilo is a local router that handles simple requests with read-only CLI tools
(System 1) and optionally sends other requests to a local Ollama model
(System 2). Every response is JSON and identifies the agent as `"Nilo"`.

Requires **Python 3.10+** and the Linux commands listed below. The router uses
only the Python standard library. System 2 requires a running Ollama server
and an installed local model.

License: [Apache-2.0](LICENSE).

## Quick start

```bash
git clone https://github.com/mattiolocoding/Nilo-System-One.git
cd Nilo-System-One
python3 nilo.py "what time is it?"
python3 nilo.py "disk space"
python3 nilo.py --help
```

Requests can be written in English or Italian.

## System 1 tools

| Intent | English / Italian examples | Fixed command |
| --- | --- | --- |
| Time and date | `what time is it?`, `che ora è?`, `date` | `date` |
| Files in the current directory | `list files`, `lista file`, `ls` | `ls -la` |
| Current user | `who am i`, `chi sono`, `whoami` | `whoami` |
| Current directory | `current directory`, `dove mi trovo?`, `pwd` | `pwd` |
| Computer name | `hostname`, `nome del computer` | `hostname` |
| Operating system | `system information`, `sistema operativo` | `uname -srm` |
| Uptime | `uptime`, `tempo di attività` | `uptime` |
| Disk space | `disk space`, `spazio su disco` | `df -h` |
| Memory | `memory usage`, `memoria disponibile` | `free -h` |

Matching accepts uppercase text, repeated spaces, trailing punctuation, and
some polite phrases such as `please show files` and
`puoi darmi la lista file please`. The entire request must match one intent.
Requests such as `tell me a joke about time`, `explain ls`, multiple intents,
and commands with arbitrary arguments go to System 2.

To extend the router, add a `TOOL_INTENTS` entry with a pattern and a fixed
command, then test both valid requests and ambiguous wording.

## Inspect a decision before execution

Inspired by the typed-decision approach of
[Rizzo Flow](https://github.com/Rizzo-AI-Academy/rizzo-flow), Nilo separates
routing decisions from execution. `decide_query()` returns an immutable
`RoutingDecision` with an action, reason, intent, and allowed command. It runs
no tools and makes no model requests. `route_query()` applies the decision.

```bash
python3 nilo.py --decide-only "list files"
python3 nilo.py --decide-only "Explain how ls works"
```

This mode returns `status: "decision"` and uses zero tokens. Every response
includes `routing.method`, `routing.action`, and `routing.reason` so the
choice remains inspectable when a tool fails or no model is configured.
The current router uses deterministic regex matching and returns no
probabilities or model logits.

Rizzo Flow informed the structured decisions, fallback behavior, and explicit
metrics. Nilo is an independent standard-library implementation; it includes
no code or model weights from that project.
Reference revision: `b9ba007ee4d2928bbab5b1d8bfe9009c3696b6de`.

## Local System 2

Enable the fallback by naming an installed model:

```bash
ollama list
python3 nilo.py --model qwen2.5:7b-instruct "Explain gravity in one sentence."
```

Or set a default for subsequent CLI invocations:

```bash
export NILO_MODEL=qwen2.5:7b-instruct
python3 nilo.py "Write a short poem about the sea."
python3 nilo.py --no-system-2 "Write a short poem about the sea."
```

`--model` overrides `NILO_MODEL`. `--no-system-2` disables the fallback even
when an environment variable is set. Without a model, complex requests return
`status: "routed_to_system_2"` with configuration instructions; no inference
occurs. System 1 requests bypass the LLM even when it is configured.

The default server is `http://127.0.0.1:11434`. Set `--ollama-url` or
`NILO_OLLAMA_URL` to change it. Only HTTP(S) origins on loopback hosts
(`localhost`, `127.0.0.1`, `::1`) are accepted. Environment proxies and HTTP
redirects are disabled. Choose a local model rather than a cloud-backed model.
The client uses [`POST /api/generate`](https://docs.ollama.com/api/generate)
with `stream: false`. Its system prompt asks Nilo to answer concisely in the
user's language.

Configurable limits:

- `--tool-timeout`: CLI process timeout, default 5 seconds.
- `--llm-timeout`: timeout for HTTP wait operations, default 60 seconds.
- `--max-tokens`: Ollama output token limit, default 256.

The HTTP timeout does not guarantee cancellation of inference on the server.
Accepted HTTP responses are limited to 1 MiB. Waiting for a model to load
counts toward the HTTP timeout.

Python API configuration is explicit; environment variables are read by the
CLI:

```python
from nilo import OllamaConfig, route_query

config = OllamaConfig(model="qwen2.5:7b-instruct", timeout=60, max_tokens=128)
result = route_query("Explain gravity in one sentence.", system_2=config)
```

## Output and metrics

- `system`: 1 for CLI tools, 2 for the fallback.
- `execution_time_ms`: elapsed time measured with `time.perf_counter()`,
  including waits and errors.
- `cost_tokens`: 0 for System 1 and a disabled fallback. For System 2, it is
  the sum of input and output token counts reported by Ollama, also available
  in `usage`. This is a token count, not a monetary cost.
- `cost_tokens: null`: usage is unknown when valid metrics are absent or the
  model request fails.
- `status: "success"`: the command succeeded or the model completed generation
  with text. A model `done_reason: "length"` indicates its output limit was
  reached.
- `status: "error"`: timeout, missing or failed command, unavailable server,
  HTTP error, or invalid/incomplete model response. The CLI exits with code 1.
- `status: "routed_to_system_2"`: no model is configured and no answer was
  generated. The CLI exits with code 0.

Token accounting follows the [Ollama usage documentation](https://docs.ollama.com/api/usage).
Latency depends on hardware, model size, and whether the model is already
loaded. Nilo makes no unmeasured speedup or savings claims.

## Security and tests

Tools are an allowlist of fixed, read-only commands and arguments.
`subprocess.run` receives separate argv entries, `shell=False`, and a timeout.
Paths, options, and shell metacharacters from a query never become command
arguments. Model output is displayed as text and never executed.

```bash
python3 -m unittest test_nilo.py -v
```

Tests cover routing, ambiguous requests, injection attempts, CLI failures,
timeouts, model configuration, and token accounting. HTTP tests use a
temporary loopback server: they require no Ollama instance, model downloads,
or external services. System 1 smoke tests require the Linux tools.

GitHub Actions runs the suite on Ubuntu with Python 3.10, 3.12, and 3.14.
