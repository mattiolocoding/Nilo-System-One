# SPDX-License-Identifier: Apache-2.0
import math
from pathlib import Path
import random
import unittest

from benchmarks.run import read_dataset, request_for, summarize, validate_answer


class BenchmarkTests(unittest.TestCase):
    def test_gold_and_metadata_never_reach_predictor(self):
        rows, _ = read_dataset(Path(__file__).parent / "benchmarks" / "cases.jsonl")
        row = rows[0]
        first = request_for(row, random.Random(1))
        changed = dict(row, gold="different", id="SECRET", language="SECRET", category="SECRET")
        self.assertEqual(first, request_for(changed, random.Random(1)))
        self.assertEqual(set(first), {"state", "questions"})
        self.assertEqual(first["questions"]["decision"]["criteria"], row["options"])
        self.assertNotEqual(list(first["questions"]["decision"]["criteria"]), list(row["options"]))

    def test_errors_and_abstentions_count_against_accuracy(self):
        common = dict(track="routing", language="en", category="negation", gold="system_2", elapsed_ms=1)
        rows = [dict(common, id="a", choice="system_2", correct=True, status="ok"),
                dict(common, id="b", choice="time", correct=False, status="ok"),
                dict(common, id="c", choice=None, correct=False, status="ok"),
                dict(common, id="d", choice=None, correct=False, status="error")]
        result = summarize(rows)
        self.assertEqual(result["accuracy"], .25)
        self.assertEqual(result["coverage"], .5)
        self.assertEqual(result["error_rate"], .25)
        self.assertEqual(result["abstention_rate"], .25)
        self.assertEqual(result["false_tool_selections"], 1)

    def test_unknown_labels_and_invalid_distributions_fail(self):
        for answer in ({"choice": "wrong"}, {"choice": []},
                       {"choice": "a", "probabilities": {"a": 1}},
                       {"choice": "a", "probabilities": {"a": math.nan, "b": 0}},
                       {"choice": "a", "probabilities": {"a": .2, "b": .2}}):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                validate_answer(answer, {"a": "A", "b": "B"})

    def test_fixture_has_disjoint_ids_and_both_tracks(self):
        rows, digest = read_dataset(Path(__file__).parent / "benchmarks" / "cases.jsonl")
        self.assertEqual(len(digest), 64)
        for track in ("routing", "general"):
            dev = {r["id"] for r in rows if r["track"] == track and r["split"] == "dev"}
            evaluation = {r["id"] for r in rows if r["track"] == track and r["split"] == "eval"}
            self.assertTrue(dev and evaluation)
            self.assertFalse(dev & evaluation)


if __name__ == "__main__":
    unittest.main()
