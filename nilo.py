#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import argparse
from dataclasses import dataclass
import http.client
import ipaddress
import json
import math
import os
import re
import subprocess
import time
from typing import Literal
import urllib.error
import urllib.parse
import urllib.request


AGENT_NAME = "Nilo"
MAX_RESPONSE_BYTES = 1_048_576
SYSTEM_PROMPT = (
    "You are Nilo, a local assistant. Answer concisely in the same language "
    "as the user's request. Respond with text only."
)


@dataclass(frozen=True)
class ToolIntent:
    name: str
    command: tuple[str, ...]
    pattern: str


@dataclass(frozen=True)
class RoutingDecision:
    action: Literal["tool", "system_2", "reject"]
    reason: str
    intent: str | None = None
    command: tuple[str, ...] = ()


# Only complete, single-intent requests match. User text never becomes argv.
TOOL_INTENTS = (
    ToolIntent("time", ("date",),
               r"(?:time|date|ora|data|orario|what(?:'s| is)? (?:the )?(?:time|date)(?: is it)?|che (?:ora|ore) (?:sono|[eè](?:['’])?)|(?:dimmi|mostra) (?:l['’])?(?:ora|data))"),
    ToolIntent("list_files", ("ls", "-la"),
               r"(?:ls|(?:list|show)(?: (?:the|current))? files|(?:(?:la )?lista|elenca|mostra)(?: (?:i|dei))? file)"),
    ToolIntent("identity", ("whoami",),
               r"(?:whoami|who am i|chi sono(?: io)?|current user|utente corrente)"),
    ToolIntent("directory", ("pwd",),
               r"(?:pwd|(?:current|working) directory|where am i|(?:directory|cartella) (?:di lavoro|corrente|attuale)|dove (?:mi trovo|sono))"),
    ToolIntent("hostname", ("hostname",),
               r"(?:hostname|host name|(?:computer|machine) name|nome (?:host|computer|del computer|della macchina))"),
    ToolIntent("system", ("uname", "-srm"),
               r"(?:uname|system info(?:rmation)?|operating system|sistema operativo|(?:informazioni|info) (?:sul )?sistema)"),
    ToolIntent("uptime", ("uptime",),
               r"(?:uptime|system uptime|tempo di attivit[aà]|da quanto (?:tempo )?[eè] acceso(?: il (?:computer|sistema))?)"),
    ToolIntent("disk", ("df", "-h"),
               r"(?:df|disk (?:space|usage)|(?:free|available) disk space|spazio (?:su disco|disco|disponibile su disco)|utilizzo disco)"),
    ToolIntent("memory", ("free", "-h"),
               r"(?:free|memory (?:usage|info)|(?:free|available) memory|memoria (?:libera|disponibile)|utilizzo (?:memoria|ram))"),
)
ALLOWED_COMMANDS = frozenset(intent.command for intent in TOOL_INTENTS)
_PREFIX = r"(?:(?:please|per favore) |(?:can|could|would) you |(?:puoi|potresti) (?:(?:darmi|mostrarmi|dire|mostrare) )?)?"
_SUFFIX = r"(?: (?:please|per favore|grazie))?[?.!]*"
_MATCHERS = tuple(
    (intent, re.compile(_PREFIX + intent.pattern + _SUFFIX, re.IGNORECASE))
    for intent in TOOL_INTENTS
)


def _positive_timeout(value: float) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def decide_query(query: str) -> RoutingDecision:
    """Return a deterministic decision without executing tools or calling an LLM."""
    if not isinstance(query, str) or not query.strip():
        return RoutingDecision("reject", "invalid_query")
    normalized = re.sub(r"[ \t]+", " ", query.strip())
    matches = [intent for intent, matcher in _MATCHERS if matcher.fullmatch(normalized)]
    if len(matches) == 1:
        intent = matches[0]
        return RoutingDecision("tool", "full_intent_match", intent.name, intent.command)
    if len(matches) > 1:
        return RoutingDecision("system_2", "ambiguous_intent_match")
    return RoutingDecision("system_2", "no_full_intent_match")


@dataclass(frozen=True)
class OllamaConfig:
    model: str
    base_url: str = "http://127.0.0.1:11434"
    timeout: float = 60.0
    max_tokens: int = 256

    def __post_init__(self):
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("An Ollama model is required")
        if not _positive_timeout(self.timeout):
            raise ValueError("LLM timeout must be finite and positive")
        if type(self.max_tokens) is not int or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if not isinstance(self.base_url, str):
            raise ValueError("Ollama URL must be a string")
        try:
            parsed = urllib.parse.urlsplit(self.base_url)
            local_host = parsed.hostname == "localhost"
            if not local_host:
                local_host = ipaddress.ip_address(parsed.hostname or "").is_loopback
            parsed.port  # Validate the port before sending any request.
        except ValueError as exc:
            raise ValueError("Ollama URL must use a local loopback host") from exc
        if (not local_host or parsed.scheme not in ("http", "https")
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("Ollama URL must be an HTTP(S) loopback origin")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def handle_system_2(query: str, config: OllamaConfig, *, output_schema=None,
                    system_prompt=SYSTEM_PROMPT):
    """Ask a local model for text; model output is never executed as a command."""
    response = {
        "system": 2, "backend": "ollama", "model": config.model,
        "query": query, "cost_tokens": None,
    }
    body = {
        "model": config.model, "prompt": query, "system": system_prompt,
        "stream": False, "options": {"num_predict": config.max_tokens},
    }
    if output_schema is not None:
        body["format"] = output_schema
        body["options"]["temperature"] = 0
    request = urllib.request.Request(
        config.base_url.rstrip("/") + "/api/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Bypass environment proxies and disallow redirects to keep queries local.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirects(),
    )
    try:
        with opener.open(request, timeout=config.timeout) as result:
            lengths = result.headers.get_all("Content-Length", [])
            transfer = result.headers.get("Transfer-Encoding")
            if len(lengths) > 1 or (lengths and transfer is not None):
                raise ValueError("Ambiguous HTTP response framing")
            expected_size = None
            if lengths:
                length = lengths[0].strip()
                if not length.isascii() or not length.isdecimal():
                    raise ValueError("Invalid HTTP Content-Length")
                expected_size = int(length)
            if transfer is not None and transfer.strip().lower() != "chunked":
                raise ValueError("Unsupported HTTP Transfer-Encoding")
            raw = result.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Ollama response exceeds 1 MiB")
        if expected_size is not None and len(raw) != expected_size:
            raise ValueError("Incomplete HTTP response body")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Ollama response must be a JSON object")
        if payload.get("error"):
            raise ValueError(str(payload["error"]))
        if payload.get("done") is not True:
            raise ValueError("Ollama generation did not complete")
        output = payload.get("response")
        if not isinstance(output, str) or not output.strip():
            raise ValueError("Ollama returned no text")
        counts = (payload.get("prompt_eval_count"), payload.get("eval_count"))
        if all(type(count) is int and count >= 0 for count in counts):
            response["usage"] = {"input_tokens": counts[0], "output_tokens": counts[1]}
            response["cost_tokens"] = sum(counts)
        response.update(status="success", output=output.strip())
        if isinstance(payload.get("done_reason"), str):
            response["done_reason"] = payload["done_reason"]
    except urllib.error.HTTPError as exc:
        response.update(status="error", error=f"Ollama HTTP {exc.code}")
        exc.close()
    except (TimeoutError, urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        response.update(status="error", error=f"Ollama request failed: {exc}")
    except (ValueError, UnicodeError) as exc:
        response.update(status="error", error=f"Invalid Ollama response: {exc}")
    return response


def handle_tool_call(command: list, *, timeout: float = 5.0):
    """Execute only fixed, read-only commands with a bounded wait and no shell."""
    if (not isinstance(command, (list, tuple)) or not command
            or any(not isinstance(arg, str) for arg in command)
            or tuple(command) not in ALLOWED_COMMANDS):
        return {"status": "error", "error": "Command is not allowlisted"}
    command = list(command)
    tool = " ".join(command)
    if not _positive_timeout(timeout):
        return {"status": "error", "tool": tool, "error": "Tool timeout must be finite and positive"}
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True,
            shell=False, timeout=timeout,
        )
        return {"status": "success", "tool": tool, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"status": "error", "tool": tool, "error": f"Command timed out after {timeout:g}s"}
    except subprocess.CalledProcessError as exc:
        return {"status": "error", "tool": tool, "error": (exc.stderr or "").strip() or f"Command exited with status {exc.returncode}"}
    except FileNotFoundError:
        return {"status": "error", "tool": tool, "error": f"Command not found: {command[0]}"}
    except (OSError, UnicodeError) as exc:
        return {"status": "error", "tool": tool, "error": str(exc)}


def route_query(query: str, *, system_2: OllamaConfig | None = None,
                tool_timeout: float = 5.0, decide_only: bool = False):
    """Resolve simple requests locally; optionally send other requests to Ollama."""
    start_time = time.perf_counter()
    decision = decide_query(query)
    if decision.action == "reject":
        response = {"status": "error", "error": "Query must be a non-empty string"}
    elif decide_only:
        response = {
            "status": "decision", "system": 1 if decision.action == "tool" else 2,
            "intent": decision.intent, "command": list(decision.command), "query": query,
        }
    elif decision.action == "tool":
        response = handle_tool_call(list(decision.command), timeout=tool_timeout)
        response.update(system=1, intent=decision.intent)
    elif system_2 is not None:
        response = handle_system_2(query, system_2)
    else:
        response = {
            "status": "routed_to_system_2", "system": 2, "query": query,
            "message": "System 2 is not configured. Set --model or NILO_MODEL to enable local Ollama.",
        }
    response["routing"] = {"method": "regex", "action": decision.action, "reason": decision.reason}
    response["agent"] = AGENT_NAME
    response["execution_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
    response.setdefault("cost_tokens", 0)
    return response


def main():
    parser = argparse.ArgumentParser(description="Nilo: local CLI router with optional Ollama fallback")
    parser.add_argument("query", nargs="*", help="Request in Italian or English")
    parser.add_argument("--list-tools", action="store_true", help="List supported intents and fixed commands without running them")
    parser.add_argument("--model", default=os.environ.get("NILO_MODEL"), help="Installed Ollama model (enables System 2)")
    parser.add_argument("--ollama-url", default=os.environ.get("NILO_OLLAMA_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--llm-timeout", type=float, default=60.0)
    parser.add_argument("--tool-timeout", type=float, default=5.0)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--no-system-2", action="store_true", help="Disable Ollama, including environment configuration")
    parser.add_argument("--decide-only", action="store_true", help="Return the routing decision without executing tools or an LLM")
    args = parser.parse_args()
    if args.list_tools:
        if args.query:
            parser.error("--list-tools does not take a query")
        start_time = time.perf_counter()
        response = {
            "agent": AGENT_NAME, "status": "success", "cost_tokens": 0,
            "tools": [{"intent": intent.name, "command": list(intent.command)} for intent in TOOL_INTENTS],
        }
        response["execution_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        print(json.dumps(response, indent=2))
        return 0
    if not args.query:
        parser.error("a query is required unless --list-tools is used")
    if not _positive_timeout(args.tool_timeout):
        parser.error("--tool-timeout must be finite and positive")
    config = None
    query = " ".join(args.query)
    if (args.model and not args.no_system_2 and not args.decide_only
            and decide_query(query).action == "system_2"):
        try:
            config = OllamaConfig(args.model, args.ollama_url, args.llm_timeout, args.max_tokens)
        except ValueError as exc:
            parser.error(str(exc))
    response = route_query(
        query, system_2=config, tool_timeout=args.tool_timeout,
        decide_only=args.decide_only,
    )
    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 1 if response["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
