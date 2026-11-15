import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('dependency_audit', Path(__file__).resolve().parents[1] / 'audit_dependencies.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DependencyAuditTests(unittest.TestCase):
    def test_exact_package_version_is_sent_and_findings_are_not_silenced(self):
        packages = [{'package': {'ecosystem': 'Maven', 'name': 'example:library'}, 'version': '1.2.3'}]
        with patch.object(audit.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps({'results': [{'vulns': [{'id': 'GHSA-example'}]}]}).encode())) as request:
            result = audit.audit(packages)
        self.assertEqual(json.loads(request.call_args.args[0].data), {'queries': packages})
        self.assertEqual(result, [{'package': 'example:library', 'version': '1.2.3', 'id': 'GHSA-example'}])

    def test_partial_provider_response_is_not_treated_as_a_clean_scan(self):
        packages = [{'package': {'ecosystem': 'PyPI', 'name': 'example'}, 'version': '1'}]
        with patch.object(audit.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"results":[]}')):
            with self.assertRaises(ValueError): audit.audit(packages)

    def test_provider_failure_propagates(self):
        with patch.object(audit.urllib.request, 'urlopen', side_effect=OSError('offline')):
            with self.assertRaises(OSError): audit.audit([{'package': {'name': 'example'}, 'version': '1'}])

    def test_individual_query_errors_or_pagination_are_not_silenced(self):
        packages = [{'package': {'name': 'example'}, 'version': '1'}]
        for result in [{'error': 'unavailable'}, {'next_page_token': 'more'}, {'vulns': None}]:
            with patch.object(audit.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps({'results': [result]}).encode())):
                with self.assertRaises(ValueError): audit.audit(packages)


if __name__ == '__main__':
    unittest.main()
