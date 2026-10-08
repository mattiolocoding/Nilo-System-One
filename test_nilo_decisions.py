# SPDX-License-Identifier: Apache-2.0
from http.server import HTTPServer
import json
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from nilo import OllamaConfig
from nilo_decisions import decide, handler_for, parse_json


REQUEST = {"state": "The user requests a refund.", "questions": {
    "route": {"type": "choice", "instructions": "Select the team.",
              "criteria": {"billing": "Payment issues", "access": "Sign-in issues"}},
    "urgent": {"type": "boolean", "instructions": "Does the user mention urgency?"},
}}
CONFIG = OllamaConfig("test-model")


class DecisionTests(unittest.TestCase):
    @patch("nilo_decisions.handle_system_2")
    def test_typed_answers_and_honest_usage(self, inference):
        inference.return_value = {"status": "success", "output": '{"route":"billing","urgent":"false"}',
                                  "cost_tokens": 47, "usage": {"input_tokens": 40, "output_tokens": 7}}
        result = decide(REQUEST, CONFIG)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["answers"]["route"]["choice"], "billing")
        self.assertIs(result["answers"]["urgent"]["value"], False)
        self.assertIsNone(result["answers"]["route"]["probabilities"])
        self.assertEqual(result["cost_tokens"], 47)
        schema = inference.call_args.kwargs["output_schema"]
        self.assertEqual(schema["properties"]["route"]["enum"], ["billing", "access"])

    @patch("nilo_decisions.handle_system_2")
    def test_invalid_requests_do_not_call_model(self, inference):
        for request in (None, {}, {"state": 3, "questions": {}},
                        {"state": "x", "questions": {"q": {"type": "shell", "instructions": "run"}}},
                        {"state": "x", "questions": {"q": {"type": "choice", "instructions": "choose", "criteria": {"a": "A"}}}}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                decide(request, CONFIG)
        inference.assert_not_called()

    @patch("nilo_decisions.handle_system_2")
    def test_bad_model_results_never_return_partial_success(self, inference):
        for output in ('{"route":"billing"}', '{"route":"shell","urgent":"false"}',
                       '{"route":"billing","urgent":false}',
                       '{"route":"billing","urgent":"false","extra":"x"}',
                       '{"route":"billing","route":"access","urgent":"false"}'):
            inference.return_value = {"status": "success", "output": output, "cost_tokens": 5}
            result = decide(REQUEST, CONFIG)
            self.assertEqual(result["status"], "error")
            self.assertNotIn("answers", result)
        inference.return_value = {"status": "error", "error": "Backend unavailable", "cost_tokens": None}
        self.assertEqual(decide(REQUEST, CONFIG)["status"], "error")

    def test_json_rejects_duplicates_and_nonfinite_numbers(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(ValueError):
                parse_json(raw)

    @patch("nilo_decisions.handle_system_2")
    def test_http_contract_and_backend_error_status(self, inference):
        server = HTTPServer(("127.0.0.1", 0), handler_for(CONFIG))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/v1/systemone"
        try:
            inference.return_value = {"status": "success", "output": '{"route":"billing","urgent":"false"}', "cost_tokens": 6}
            request = urllib.request.Request(url, json.dumps(REQUEST).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response)["answers"]["route"]["choice"], "billing")
            inference.return_value = {"status": "error", "error": "Backend unavailable", "cost_tokens": None}
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code, 502)
            caught.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
