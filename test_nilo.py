# SPDX-License-Identifier: Apache-2.0

from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import re
import subprocess
import threading
import unittest
from unittest.mock import patch

from nilo import SYSTEM_PROMPT, TOOL_INTENTS, OllamaConfig, decide_query, handle_tool_call, main, route_query

class TestNilo(unittest.TestCase):

    def _assert_metrics(self, result):
        self.assertEqual(result["cost_tokens"], 0)
        self.assertIn("execution_time_ms", result)
        self.assertGreaterEqual(result["execution_time_ms"], 0)
        self.assertEqual(result["agent"], "Nilo")

    def test_system_1_routing_time(self):
        result = route_query("what time is it?")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool"], "date")
        self.assertIn("output", result)
        self._assert_metrics(result)

    def test_system_1_routing_ora(self):
        result = route_query("che ora e'")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool"], "date")
        self.assertIn("output", result)
        self._assert_metrics(result)

    def test_system_1_routing_ls(self):
        result = route_query("ls  ")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool"], "ls -la")
        self.assertIn("output", result)
        self._assert_metrics(result)

    def test_system_1_routing_lista_file(self):
        result = route_query("puoi darmi la lista file please")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool"], "ls -la")
        self.assertIn("output", result)
        self._assert_metrics(result)

    def test_system_1_routing_whoami(self):
        result = route_query("whoami")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool"], "whoami")
        self.assertIn("output", result)
        self._assert_metrics(result)

        result2 = route_query("who am i ")
        self.assertEqual(result2["status"], "success")
        self.assertEqual(result2["tool"], "whoami")
        self.assertIn("output", result2)
        self._assert_metrics(result2)

    def test_system_2_routing_complex(self):
        result = route_query("tell me a joke about time")
        self.assertEqual(result["status"], "routed_to_system_2")
        self.assertEqual(result["query"], "tell me a joke about time")
        self._assert_metrics(result)

class TestSafeRouting(unittest.TestCase):
    def test_complete_request_grammars_and_unicode(self):
        cases = {
            "Could you show my login name?": "identity",
            "Display the files in the current folder.": "list_files",
            "What operating system am I using?": "system",
            "How much available disk space do I have?": "disk",
            "quanta ram e\u0300 disponibile?": "memory",
            "Wie lange läuft der Computer?": "uptime",
            "¿Qué hora es?": "time",
            "Quel est le nom de cette machine ?": "hostname",
        }
        for query, intent in cases.items():
            with self.subTest(query=query):
                self.assertEqual(decide_query(query).intent, intent)
        for query in (
            "Do not show my login name", "Mostrami il percorso della cartella /etc",
            "Display the files in the current folder and delete them",
            "Explique quel est le nom de cette machine", "Wie lange läuft der Computer; ls",
            "How much RAM is free on server.example.com?", "¿Qué hora es en Tokio?",
        ):
            with self.subTest(query=query):
                self.assertEqual(decide_query(query).action, "system_2")

    @patch("nilo.subprocess.run")
    def test_overlapping_intents_fall_back_without_executing(self, run):
        matchers = ((TOOL_INTENTS[5], re.compile("status")), (TOOL_INTENTS[6], re.compile("status")))
        with patch("nilo._MATCHERS", matchers):
            result = route_query("status")
        self.assertEqual(result["status"], "routed_to_system_2")
        self.assertEqual(result["routing"]["reason"], "ambiguous_intent_match")
        run.assert_not_called()

    @patch("nilo.subprocess.run")
    @patch("nilo.urllib.request.build_opener")
    def test_typed_decision_has_no_side_effects(self, opener, run):
        decision = decide_query("lista file")
        self.assertEqual(decision.action, "tool")
        self.assertEqual(decision.intent, "list_files")
        self.assertEqual(decision.command, ("ls", "-la"))
        self.assertEqual(decision.reason, "full_intent_match")
        self.assertEqual(decide_query("explain ls").action, "system_2")
        self.assertEqual(decide_query("").action, "reject")
        opener.assert_not_called()
        run.assert_not_called()

    @patch("nilo.subprocess.run")
    @patch("nilo.urllib.request.build_opener")
    def test_decision_only_bypasses_both_systems(self, opener, run):
        for query, action in (("ls", "tool"), ("explain ls", "system_2")):
            with self.subTest(query=query):
                result = route_query(query, system_2=OllamaConfig("unused-model"), decide_only=True)
                self.assertEqual(result["status"], "decision")
                self.assertEqual(result["routing"]["action"], action)
                self.assertEqual(result["cost_tokens"], 0)
                self.assertGreaterEqual(result["execution_time_ms"], 0)
        opener.assert_not_called()
        run.assert_not_called()

    def test_new_intents_and_languages(self):
        cases = {
            "pwd": "pwd", "dove mi trovo?": "pwd",
            "current directory": "pwd", "hostname": "hostname",
            "nome del computer": "hostname", "system information": "uname -srm",
            "sistema operativo": "uname -srm", "uptime": "uptime",
            "tempo di attività": "uptime", "disk space": "df -h",
            "spazio su disco": "df -h", "memory usage": "free -h",
            "memoria disponibile": "free -h", "che ora è?": "date",
            "PLEASE SHOW FILES!": "ls -la", "potresti mostrarmi la lista file?": "ls -la",
        }
        for query, tool in cases.items():
            with self.subTest(query=query):
                result = route_query(query)
                self.assertEqual(result["status"], "success")
                self.assertEqual(result["tool"], tool)
                self.assertEqual(result["system"], 1)
                self.assertEqual(result["cost_tokens"], 0)

    @patch("nilo.subprocess.run")
    def test_ambiguous_and_injection_queries_do_not_run_tools(self, run):
        for query in (
            "time && touch /tmp/nilo-injection", "ls; whoami", "$(whoami)",
            "ls | cat", "ls\nwhoami", "ls /etc", "ls -R", "free --help",
            "tell me a story about time", "explain ls", "how to free memory",
            "che ora è e chi sono", "list files and delete them", "who am i as a person",
        ):
            with self.subTest(query=query):
                result = route_query(query)
                self.assertEqual(result["status"], "routed_to_system_2")
                self.assertEqual(result["query"], query)
        run.assert_not_called()

    @patch("nilo.urllib.request.build_opener")
    def test_system_1_bypasses_configured_llm(self, opener):
        result = route_query("whoami", system_2=OllamaConfig("unused-model"))
        self.assertEqual(result["system"], 1)
        self.assertEqual(result["cost_tokens"], 0)
        opener.assert_not_called()

    @patch("nilo.subprocess.run")
    def test_allowlist_blocks_arbitrary_commands_and_flags(self, run):
        for command in (["sh", "-c", "whoami"], ["rm", "file"], ["ls", "-R"], [], ["date", ";whoami"], None, "whoami", [["whoami"]], [42]):
            with self.subTest(command=command):
                self.assertEqual(handle_tool_call(command)["status"], "error")
        run.assert_not_called()

    @patch("nilo.subprocess.run")
    def test_argv_shell_and_timeout(self, run):
        run.return_value = subprocess.CompletedProcess(["ls", "-la"], 0, stdout="files\n", stderr="")
        result = route_query("ls", tool_timeout=2.0)
        run.assert_called_once_with(
            ["ls", "-la"], check=True, capture_output=True, text=True,
            shell=False, timeout=2.0,
        )
        self.assertEqual(result["output"], "files")

    @patch("nilo.subprocess.run")
    def test_tool_failures_are_json_errors(self, run):
        cases = (
            (FileNotFoundError(), "Command not found"),
            (subprocess.TimeoutExpired(["date"], 0.1), "timed out"),
            (subprocess.CalledProcessError(3, ["date"], stderr="denied\n"), "denied"),
            (subprocess.CalledProcessError(3, ["date"]), "status 3"),
            (PermissionError("permission denied"), "permission denied"),
        )
        for error, message in cases:
            with self.subTest(error=error):
                run.side_effect = error
                result = route_query("time")
                self.assertEqual(result["status"], "error")
                self.assertIn(message, result["error"])
                self.assertEqual(result["cost_tokens"], 0)
                self.assertIn("execution_time_ms", result)

    @patch("nilo.subprocess.run")
    def test_invalid_tool_timeout(self, run):
        for timeout in (0, -1, float("nan"), float("inf"), True, None, "5", 10 ** 1000):
            with self.subTest(timeout=timeout):
                self.assertEqual(route_query("time", tool_timeout=timeout)["status"], "error")
        run.assert_not_called()

    def test_invalid_queries(self):
        for query in ("", " \t", None, 42):
            with self.subTest(query=query):
                result = route_query(query)
                self.assertEqual(result["status"], "error")
                self.assertIn("execution_time_ms", result)

    @patch("nilo.time.time", side_effect=AssertionError("wall clock used"))
    def test_execution_metric_uses_monotonic_clock(self, wall_clock):
        self.assertGreaterEqual(route_query("whoami")["execution_time_ms"], 0)


class TestOllamaConfig(unittest.TestCase):
    def test_rejects_nonlocal_and_malformed_origins(self):
        for url in (
            "http://example.com", "http://192.168.1.1:11434", "file:///etc/passwd",
            "http://localhost.evil.test", "http://user:pass@localhost:11434",
            "http://127.0.0.1/api", "http://127.0.0.1?secret=x", "http://127.0.0.1#x",
            "http://127.0.0.1:bad", "http://[broken",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                OllamaConfig("test-model", base_url=url)

    def test_accepts_loopback_origins(self):
        for url in ("http://localhost:11434", "http://127.0.0.1:11434/", "http://[::1]:11434"):
            with self.subTest(url=url):
                self.assertEqual(OllamaConfig("test-model", base_url=url).base_url, url)

    def test_rejects_invalid_limits_and_empty_model(self):
        for kwargs in (
            {"model": " "}, {"model": None}, {"base_url": None},
            {"timeout": 0}, {"timeout": float("inf")}, {"timeout": True},
            {"timeout": "5"}, {"timeout": None}, {"timeout": 10 ** 1000},
            {"timeout": float("nan")}, {"max_tokens": 0}, {"max_tokens": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                OllamaConfig(**({"model": "test-model"} | kwargs))


class TestOllamaHTTP(unittest.TestCase):
    """Exercise real local HTTP requests without requiring an installed LLM."""

    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                cls.request_path = self.path
                cls.request_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                cls.request_count += 1
                if cls.raw_http is not None:
                    self.wfile.write(cls.raw_http)
                    self.close_connection = True
                    return
                body = cls.body if isinstance(cls.body, bytes) else json.dumps(cls.body).encode()
                self.send_response(cls.http_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", cls.content_length or str(len(body)))
                if cls.http_status == 302:
                    self.send_header("Location", cls.base_url + "/redirected")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        type(self).http_status = 200
        type(self).request_count = 0
        type(self).raw_http = None
        type(self).content_length = None
        type(self).body = {
            "response": "Risposta locale", "done": True,
            "prompt_eval_count": 12, "eval_count": 7, "done_reason": "stop",
        }
        self.config = OllamaConfig("test-model", self.base_url, timeout=2, max_tokens=32)

    def test_generation_request_and_token_accounting(self):
        query = "Spiega la gravità in una frase."
        result = route_query(query, system_2=self.config)
        self.assertEqual(self.request_path, "/api/generate")
        self.assertEqual(self.request_body, {
            "model": "test-model", "prompt": query, "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {"num_predict": 32},
        })
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["agent"], "Nilo")
        self.assertEqual(result["system"], 2)
        self.assertEqual(result["output"], "Risposta locale")
        self.assertEqual(result["usage"], {"input_tokens": 12, "output_tokens": 7})
        self.assertEqual(result["cost_tokens"], 19)
        self.assertGreaterEqual(result["execution_time_ms"], 0)

    def test_truncated_content_length_is_not_success(self):
        type(self).content_length = str(len(json.dumps(self.body).encode()) + 50)
        result = route_query("complex request", system_2=self.config)
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["cost_tokens"])

    def test_invalid_content_length_is_not_success(self):
        for value in ("-1", "not-a-number"):
            with self.subTest(value=value):
                type(self).content_length = value
                result = route_query("complex request", system_2=self.config)
                self.assertEqual(result["status"], "error")
                self.assertIsNone(result["cost_tokens"])

    def test_http_protocol_errors_are_json_errors(self):
        for raw in (
            b"NOT-HTTP\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n20\r\nshort",
        ):
            with self.subTest(raw=raw):
                type(self).raw_http = raw
                result = route_query("complex request", system_2=self.config)
                self.assertEqual(result["status"], "error")
                self.assertIsNone(result["cost_tokens"])
                self.assertGreaterEqual(result["execution_time_ms"], 0)

    def test_complete_chunked_response_succeeds(self):
        body = json.dumps(self.body).encode()
        type(self).raw_http = (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            + f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"
        )
        result = route_query("complex request", system_2=self.config)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["cost_tokens"], 19)

    def test_ambiguous_http_framing_is_rejected(self):
        body = json.dumps(self.body).encode()
        for headers in (
            b"Content-Length: 1\r\nContent-Length: 2\r\n",
            b"Content-Length: 1\r\nTransfer-Encoding: chunked\r\n",
            b"Transfer-Encoding: unsupported\r\n",
        ):
            with self.subTest(headers=headers):
                type(self).raw_http = b"HTTP/1.1 200 OK\r\n" + headers + b"\r\n" + body
                result = route_query("complex request", system_2=self.config)
                self.assertEqual(result["status"], "error")
                self.assertIsNone(result["cost_tokens"])

    def test_missing_or_invalid_usage_is_unknown(self):
        for counts in ({}, {"prompt_eval_count": -1, "eval_count": 7}, {"prompt_eval_count": True, "eval_count": 7}):
            with self.subTest(counts=counts):
                type(self).body = {"response": "text", "done": True} | counts
                result = route_query("complex request", system_2=self.config)
                self.assertEqual(result["status"], "success")
                self.assertIsNone(result["cost_tokens"])

    def test_http_error_and_redirect(self):
        for status in (404, 500, 302):
            with self.subTest(status=status):
                type(self).http_status = status
                type(self).request_count = 0
                result = route_query("complex request", system_2=self.config)
                self.assertEqual(result["status"], "error")
                self.assertIn(str(status), result["error"])
                self.assertEqual(self.request_count, 1)
                self.assertIsNone(result["cost_tokens"])

    def test_invalid_or_incomplete_response_is_not_success(self):
        for body in (
            b"not json", b"\xff", [], {"error": "model missing"},
            {"response": "partial", "done": False}, {"response": "", "done": True},
            {"response": 42, "done": True}, b"x" * 1_048_577,
        ):
            with self.subTest(body_type=type(body).__name__):
                type(self).body = body
                result = route_query("complex request", system_2=self.config)
                self.assertEqual(result["status"], "error")
                self.assertIsNone(result["cost_tokens"])

    @patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1", "no_proxy": "", "NO_PROXY": ""})
    def test_environment_proxy_is_bypassed(self):
        self.assertEqual(route_query("complex request", system_2=self.config)["status"], "success")

    @patch("nilo.subprocess.run")
    def test_model_generated_shell_text_is_not_executed(self, run):
        type(self).body["response"] = "$(whoami); rm -rf /"
        result = route_query("complex request", system_2=self.config)
        self.assertEqual(result["output"], "$(whoami); rm -rf /")
        run.assert_not_called()

    @patch("nilo.urllib.request.OpenerDirector.open", side_effect=TimeoutError("timeout"))
    def test_request_timeout(self, open_request):
        result = route_query("complex request", system_2=self.config)
        self.assertEqual(result["status"], "error")
        self.assertIn("timeout", result["error"])
        self.assertIsNone(result["cost_tokens"])

    def test_unavailable_server(self):
        # A bound socket reserves the port without accepting HTTP connections.
        import socket
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            config = OllamaConfig("test-model", f"http://127.0.0.1:{reserved.getsockname()[1]}", timeout=0.1)
            result = route_query("complex request", system_2=config)
        self.assertEqual(result["status"], "error")
        self.assertIn("Ollama request failed", result["error"])


class TestCLI(unittest.TestCase):
    @patch.dict(os.environ, {"NILO_MODEL": "test-model", "NILO_OLLAMA_URL": "http://remote.invalid"})
    @patch("nilo.subprocess.run")
    @patch("nilo.urllib.request.build_opener")
    def test_list_tools_without_query_or_execution(self, opener, run):
        stream = io.StringIO()
        with patch("sys.argv", ["nilo.py", "--list-tools"]), redirect_stdout(stream):
            self.assertEqual(main(), 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result["agent"], "Nilo")
        self.assertEqual(result["cost_tokens"], 0)
        self.assertIn({"intent": "disk", "command": ["df", "-h"]}, result["tools"])
        opener.assert_not_called()
        run.assert_not_called()

    def test_missing_query_is_a_cli_error(self):
        with patch("sys.argv", ["nilo.py"]), redirect_stdout(io.StringIO()):
            from contextlib import redirect_stderr
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)

    def test_list_tools_rejects_a_query(self):
        from contextlib import redirect_stderr
        with patch("sys.argv", ["nilo.py", "--list-tools", "ls"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)

    @patch.dict(os.environ, {"NILO_MODEL": "test-model", "NILO_OLLAMA_URL": "http://remote.invalid"})
    @patch("nilo.urllib.request.build_opener")
    def test_decision_and_tools_ignore_unused_model_configuration(self, opener):
        for args in (["--decide-only", "complex request"], ["whoami"]):
            with self.subTest(args=args):
                stream = io.StringIO()
                with patch("sys.argv", ["nilo.py"] + args), redirect_stdout(stream):
                    self.assertEqual(main(), 0)
                self.assertIn(json.loads(stream.getvalue())["status"], ("success", "decision"))
        opener.assert_not_called()

    @patch("nilo.subprocess.run")
    def test_decision_only_cli(self, run):
        stream = io.StringIO()
        with patch("sys.argv", ["nilo.py", "--decide-only", "ls"]), redirect_stdout(stream):
            self.assertEqual(main(), 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result["status"], "decision")
        self.assertEqual(result["command"], ["ls", "-la"])
        run.assert_not_called()

    @patch.dict(os.environ, {"NILO_MODEL": "configured-model"})
    @patch("nilo.route_query")
    def test_environment_enables_model(self, route):
        route.return_value = {"status": "success"}
        with patch("sys.argv", ["nilo.py", "complex request"]), redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        self.assertEqual(route.call_args.kwargs["system_2"].model, "configured-model")

    @patch.dict(os.environ, {"NILO_MODEL": "configured-model"})
    @patch("nilo.route_query")
    def test_cli_model_overrides_environment(self, route):
        route.return_value = {"status": "success"}
        with patch("sys.argv", ["nilo.py", "--model", "override-model", "complex request"]), redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(route.call_args.kwargs["system_2"].model, "override-model")

    @patch.dict(os.environ, {"NILO_MODEL": "configured-model"})
    @patch("nilo.urllib.request.build_opener")
    def test_disable_overrides_environment(self, opener):
        stream = io.StringIO()
        with patch("sys.argv", ["nilo.py", "--no-system-2", "complex request"]), redirect_stdout(stream):
            self.assertEqual(main(), 0)
        self.assertEqual(json.loads(stream.getvalue())["status"], "routed_to_system_2")
        opener.assert_not_called()

    @patch("nilo.route_query", return_value={"status": "error", "error": "unavailable"})
    def test_error_exit_code(self, route):
        with patch("sys.argv", ["nilo.py", "time"]), redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 1)


if __name__ == '__main__':
    unittest.main()
