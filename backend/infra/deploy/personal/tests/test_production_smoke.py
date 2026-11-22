"""Exercise the production smoke journey against a local HTTP server."""
import json
import sys
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / '.github/scripts'))
import production_release as production


NOTICE_ID = '01a1da18-0de9-7000-a63d-713d0216d0d5'
DETAIL_PATH = f'/api/v1/notices/{NOTICE_ID}'
BENEFITS_PATH = f'/api/v1/eligibility/notices/{NOTICE_ID}/benefits'


class ProductionSmoke(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.responses = {
            production.ACTIVE_NOTICES_PATH: {'items': [{'id': NOTICE_ID}]},
            DETAIL_PATH: {'header': {'id': NOTICE_ID, 'field': 'HOUSING', 'title': 'Local fixture'}},
            BENEFITS_PATH: [],
        }
        calls, responses = self.calls, self.responses

        class Handler(BaseHTTPRequestHandler):
            def handle_request(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                calls.append((self.command, self.path, body))
                if self.path not in responses:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(responses[self.path]).encode('utf-8'))

            do_GET = handle_request
            do_POST = handle_request

            def log_message(self, *_args):
                pass

        server = self.enterContext(HTTPServer(('127.0.0.1', 0), Handler))
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        self.origin = f'http://127.0.0.1:{server.server_port}'

    def test_public_notice_and_benefits_use_an_empty_applicant(self):
        self.responses[BENEFITS_PATH] = [{'id': 'benefit-1', 'title': 'Local benefit', 'overall': 'NEEDS_INPUT'}]
        production.smoke_notice_journey(self.origin)
        self.assertEqual([(method, path) for method, path, _ in self.calls], [
            ('GET', production.ACTIVE_NOTICES_PATH), ('GET', DETAIL_PATH), ('POST', BENEFITS_PATH),
        ])
        self.assertEqual(json.loads(self.calls[-1][2]), {'applicant': {}})

    def test_notice_with_no_related_benefits_passes(self):
        production.smoke_notice_journey(self.origin)
        self.assertEqual(self.calls[-1][:2], ('POST', BENEFITS_PATH))

    def test_empty_notice_list_skips_detail_and_benefits(self):
        self.responses[production.ACTIVE_NOTICES_PATH] = {'items': []}
        production.smoke_notice_journey(self.origin)
        self.assertEqual(self.calls, [('GET', production.ACTIVE_NOTICES_PATH, b'')])

    def test_wrong_notice_detail_fails_the_journey(self):
        self.responses[DETAIL_PATH] = {'header': {'id': 'unrelated', 'field': 'HOUSING', 'title': 'Wrong'}}
        with self.assertRaisesRegex(RuntimeError, 'did not match'):
            production.smoke_notice_journey(self.origin)

    def test_invalid_benefit_payload_fails_the_journey(self):
        self.responses[BENEFITS_PATH] = {'items': []}
        with self.assertRaisesRegex(RuntimeError, 'invalid response'):
            production.smoke_notice_journey(self.origin)
