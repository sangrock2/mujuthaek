"""Java 수신부와 공유하는 정상·오류 입력의 동일한 판정 및 오류 출력 보호."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validate_contracts as contract

CASES = json.loads((ROOT / "tests/fixtures/extraction-boundaries.json").read_text(encoding="utf-8"))


class SharedBoundaryTest(unittest.TestCase):
    """CI는 unittest로 돌리므로(contracts/requirements-dev.txt에 pytest 없음) 사례마다 subTest로 나눕니다."""

    def test_shared_boundary(self):
        for case in CASES["cases"]:
            with self.subTest(case=case["name"]):
                value = copy.deepcopy(contract.load(ROOT / "examples" / CASES["base"]))
                for op in case["operations"]:
                    parent, _, key = op["path"].rpartition("/")
                    node = contract.resolve(value, parent)
                    key = int(key) if isinstance(node, list) else key
                    if op.get("remove"):
                        del node[key]
                    else:
                        node[key] = op["value"]
                errors = contract.validate(value, "events/extraction.completed.v1.json")
                self.assertEqual(not errors, case["valid"], errors)
                if case["errorCode"]:
                    self.assertTrue(any(error.startswith(case["errorCode"] + " ") for error in errors), errors)
                self.assertNotIn("review-placeholder-not-a-real-key", json.dumps(errors))


if __name__ == "__main__":
    unittest.main()
