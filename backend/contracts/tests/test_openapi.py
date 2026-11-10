"""공고 API 명세(openapi/notice.v1.json)가 깨지지 않았는지: OpenAPI 3.1 모양, 참조가 모두 풀림, 스키마가 JSON Schema로 올바름.

경로·요청 값이 컨트롤러와 같은지는 services/api의 NoticeOpenApiSyncTest가 봅니다."""

import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "openapi/notice.v1.json"
METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def refs(node, found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                found.append(value)
            else:
                refs(value, found)
    elif isinstance(node, list):
        for value in node:
            refs(value, found)
    return found


def resolve(document, ref):
    """이 문서 안의 참조(#/...)만 씁니다."""
    node = document
    for part in [p for p in ref.removeprefix("#").split("/") if p]:
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def operations(document):
    for path, item in document["paths"].items():
        for method, operation in item.items():
            if method in METHODS:
                yield path, method, operation


class OpenApiTest(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(SPEC.read_text(encoding="utf-8"))

    def test_is_openapi_31_document(self):
        self.assertEqual("3.1.0", self.document["openapi"])
        self.assertTrue(self.document["info"]["title"])
        self.assertTrue(self.document["info"]["version"])
        self.assertTrue(self.document["paths"])

    def test_all_references_are_local_and_resolve(self):
        for ref in refs(self.document):
            with self.subTest(ref=ref):
                self.assertTrue(ref.startswith("#/"), ref)
                self.assertIsInstance(resolve(self.document, ref), dict)

    def test_component_schemas_are_valid_json_schema(self):
        for name, schema in self.document["components"]["schemas"].items():
            with self.subTest(schema=name):
                local = json.loads(json.dumps(schema).replace('"#/components/', '"urn:notice#/components/'))
                Draft202012Validator.check_schema(local)

    def test_required_fields_are_declared(self):
        for name, schema in self.document["components"]["schemas"].items():
            for field in schema.get("required", []):
                with self.subTest(schema=name, field=field):
                    self.assertIn(field, schema["properties"])

    def test_operations_have_unique_ids_and_json_success_response(self):
        seen = set()
        for path, method, operation in operations(self.document):
            with self.subTest(operation=f"{method.upper()} {path}"):
                self.assertNotIn(operation["operationId"], seen)
                seen.add(operation["operationId"])
                success = operation["responses"]["200"]
                self.assertIn("application/json", success["content"])

    def test_path_parameters_match_path_template(self):
        for path, method, operation in operations(self.document):
            with self.subTest(operation=f"{method.upper()} {path}"):
                params = [p if "$ref" not in p else resolve(self.document, p["$ref"]) for p in operation.get("parameters", [])]
                declared = {p["name"] for p in params if p["in"] == "path"}
                self.assertEqual(set(re.findall(r"\{([^}]+)\}", path)), declared)
                self.assertTrue(all(p["required"] for p in params if p["in"] == "path"))
                names = [(p["in"], p["name"]) for p in params]
                self.assertEqual(len(names), len(set(names)))

    def test_errors_are_problem_details_with_known_codes(self):
        codes = set(self.document["components"]["schemas"]["Problem"]["properties"]["code"]["enum"])
        self.assertTrue({"VALIDATION_FAILED", "INVALID_CURSOR", "NOT_FOUND", "NOTICE_NOT_FOUND", "METHOD_NOT_ALLOWED"} <= codes)
        for path, method, operation in operations(self.document):
            for status, response in operation["responses"].items():
                if status.startswith("2"):
                    continue
                with self.subTest(operation=f"{method.upper()} {path}", status=status):
                    response = resolve(self.document, response["$ref"]) if "$ref" in response else response
                    schema = response["content"]["application/problem+json"]["schema"]
                    self.assertEqual({"$ref": "#/components/schemas/Problem"}, schema)


if __name__ == "__main__":
    unittest.main()
